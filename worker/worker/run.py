"""1회 수집 사이클: 상품별 어댑터 조회 → 스냅샷 저장 → 판정 → 알림."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .adapters import ADAPTERS, get_adapter
from .adapters.base import AdapterError, BudgetExceeded
from .baseline import compute_baseline, confirms_suspect, dominant_seller, judge, needs_confirmation, seller_changes
from .risk import assess_risk, guess_model_no
from .decision import decide
from .sales import buy_timing, upcoming_sales
from .trend import trend_pct
from statistics import median
from .config import settings
from .models import Alert, PriceSnapshot, Product, is_manual_only
from .notify import dispatch
from .storage import Storage

log = logging.getLogger("worker")


MANUAL_RECHECK_HOURS = 24 * 7   # 자동 수집 불가(robots.txt) 상품은 일주일에 한 번만 다시 시도


def _due(product: Product, min_interval_hours: float) -> bool:
    if is_manual_only(product.last_error):
        min_interval_hours = max(min_interval_hours, MANUAL_RECHECK_HOURS)
    if not min_interval_hours or not product.last_fetched_at:
        return True
    return datetime.now(timezone.utc) - product.last_fetched_at >= timedelta(hours=min_interval_hours)


def process_product(store: Storage, product: Product, delay: float = 1.0) -> Alert | None:
    try:
        adapter = get_adapter(product)
    except AdapterError as e:
        log.warning("[%s] %s", product.site, e)
        store.mark_fetch(product, str(e))
        return None

    if not _due(product, adapter.min_interval_hours):
        log.debug("[%s] %s — 갱신 주기 전, 건너뜀", product.site, product.title[:40])
        return None

    try:
        quote = adapter.fetch(product)
    except BudgetExceeded as e:
        log.info("%s", e)
        return None
    except AdapterError as e:
        if is_manual_only(str(e)):   # 사이트가 자동 수집을 금지 — 실패가 아니라 '북마클릿 전용'. 세지도, 중단하지도 않는다
            log.info("[%s] %s: 자동 수집 불가(robots.txt) — 북마클릿/확장 전용, 7일 뒤 재확인", product.site, product.title[:40])
            store.mark_fetch(product, str(e), count=False)
            return None
        log.warning("[%s] %s: %s", product.site, product.title[:40], e)
        store.mark_fetch(product, str(e))
        return _maybe_pause(store, product, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("[%s] 예외 %s", product.site, e)
        store.mark_fetch(product, f"{type(e).__name__}: {e}")
        return _maybe_pause(store, product, f"{type(e).__name__}: {e}")
    finally:
        time.sleep(delay)  # 사이트 예의
    store.mark_fetch(product, None)

    # 메타데이터 보강 (제목/이미지/모델명은 처음 성공 시 채움)
    changed = False
    if quote.title and (not product.title or product.title == product.url):
        product.title, changed = quote.title, True
    if quote.image_url and not product.image_url:
        product.image_url, changed = quote.image_url, True
    if quote.model_no and not product.model_no:
        product.model_no, changed = quote.model_no, True
    if not product.model_no and (guessed := guess_model_no(product.title or "")):
        product.model_no, changed = guessed, True
    if quote.external_id and not product.external_id:
        product.external_id, changed = quote.external_id, True
    if quote.currency and quote.currency != product.currency:   # 사이트가 말한 통화가 등록 시 추정과 다르면 따른다 (웹 capture 와 동일)
        product.currency, changed = quote.currency, True
    if changed:
        store.update_product(product)

    us = store.settings_for(product.user_id)
    history = store.history(product.id, max(us.window_days, 365))
    snap = PriceSnapshot(product.id, quote.price, quote.currency, quote.seller, quote.in_stock, list_price=quote.list_price)

    # 극단값 확인: 기준선 대비 -40% 이상이면 이번엔 기록만 하고(suspect), 다음 수집에서 같은 수준이면 확정.
    pre_baseline = compute_baseline(history, us.window_days)
    if needs_confirmation(snap, history, pre_baseline):
        snap.suspect = True
        store.add_snapshot(snap)
        store.update_risk(product, product.risk_level or "low", product.risk_reasons or "")
        log.info("[%s] %s → %s %s ⏳ 극단값 (기준선 %.0f) — 다음 수집에서 확인 후 알림", product.site, product.title[:40],
                 quote.price, quote.currency, pre_baseline or 0)
        return None
    if confirms_suspect(snap, history):
        store.confirm_suspects(product.id, snap.price)   # 같은 수준이 두 번 → 그 수준의 suspect 만 승격 (예전 파싱 오류 값은 그대로 제외)
        for h in history:
            if h.suspect and abs(h.price - snap.price) <= snap.price * 0.05:
                h.suspect = False

    verdict = judge(snap, history, us.threshold_pct, us.window_days, product.target_price)
    store.add_snapshot(snap)
    log.info("[%s] %s → %s %s (기준선 %s, %s%s%s)", product.site, product.title[:40], quote.price, quote.currency,
             f"{verdict.baseline:.0f}" if verdict.baseline else "-", verdict.kind or "정상",
             f", 표시할인 {verdict.claimed_pct:.0f}%" if verdict.claimed_pct else "",
             f", {verdict.seller_changed}" if verdict.seller_changed else "")

    # 정품 리스크 (확정 아님 — 신호의 합). 같은 모델·같은 통화의 다른 상품 최신가 중앙값과 교차 비교.
    cross = None
    if product.model_no:
        others = store.latest_prices_by_model(product.model_no, quote.currency, product.id)
        cross = float(median(others)) if others else None
    risk = assess_risk(product.title, product.site, quote.price, quote.seller, verdict.baseline, cross,
                       product.model_no, dominant_seller(history), product.verified,
                       seller_changes(history + [snap], us.window_days))
    store.update_risk(product, risk.level, risk.text)
    if risk.level != "low":
        log.info("  ⚠ 정품 리스크 %s: %s", risk.level, risk.text)

    if not verdict.triggered:
        return None
    last = store.last_alert_at(product.id, verdict.kind)
    cooldown = settings.alert_cooldown_hours * (7 if verdict.kind == "fake" else 1)  # 가짜 할인은 주 1회만
    if last and datetime.now(timezone.utc) - last < timedelta(hours=cooldown):
        return None
    note = verdict.seller_changed
    if verdict.kind == "fake" and verdict.claimed_pct:
        note = f"표시 할인 {verdict.claimed_pct:.0f}% 지만 평소 가격과 차이 {verdict.pct or 0:.1f}%"
    if risk.level == "high" and verdict.kind in ("drop", "low", "target"):
        note = (note + " · " if note else "") + f"가격이 비정상적으로 낮습니다 — 판매자를 확인하세요 (정품 리스크 높음: {risk.text})"
    if verdict.kind in ("drop", "low", "target"):
        drop_now = verdict.pct is not None and verdict.pct >= us.threshold_pct
        timing = buy_timing(drop_now, upcoming_sales(product.country, product.site, product.category or "전자"))
        d = decide(verdict.pct, us.threshold_pct, risk.level, verdict.fake,
                   (quote.price <= product.target_price) if product.target_price else None,
                   wait_label=timing.label if timing.verdict == "wait" else None,
                   trend_pct=trend_pct(history + [snap]))
        note = (note + " · " if note else "") + d.text
    alert = Alert(product.id, verdict.kind, quote.price, verdict.baseline, verdict.pct, product.user_id, note=note)
    _deliver(store, product, us, alert)
    return alert


def _deliver(store: Storage, product: Product, us, alert: Alert) -> None:
    """digest 설정이면 저장만(notified=False) → `worker digest` 가 하루 3회 모아 발송. 아니면 즉시 발송.
    목표가 도달(target)은 instant_target 이면 다이제스트를 건너뛴다."""
    if us.digest and not (us.instant_target and alert.kind == "target"):
        alert.notified = False
        store.add_alert(alert)
        log.info("  ⚑ 알림 %s → 다이제스트 대기 (아침·점심·저녁)", alert.kind)
        return
    store.add_alert(alert)
    sent, expired = dispatch(alert, product, us, store.push_subscriptions(product.user_id))
    for ep in expired:
        store.remove_push_subscription(ep)
    log.info("  ⚑ 알림 %s 발송=%s", alert.kind, sent or "앱 내")


PAUSE_AFTER_FAILS = 10


def _maybe_pause(store: Storage, product: Product, error: str) -> Alert | None:
    """연속 실패가 누적되면 추적을 자동 중단하고 사용자에게 알린다 (kind=paused)."""
    if product.fail_count + 1 < PAUSE_AFTER_FAILS:
        return None
    store.set_active(product.id, False)
    us = store.settings_for(product.user_id)
    hist = store.history(product.id, 365)
    last_price = hist[-1].price if hist else 0.0
    alert = Alert(product.id, "paused", last_price, None, None, product.user_id,
                  note=f"수집이 {PAUSE_AFTER_FAILS}회 연속 실패해 추적을 중단했습니다 ({error[:80]}). 북마클릿으로 직접 기록하거나 상세에서 재개하세요.")
    _deliver(store, product, us, alert)
    log.warning("  ⏸ 자동 중단: %s", product.title[:40])
    return alert


def run_once(store: Storage) -> int:
    for a in ADAPTERS:
        a.reset_budget()
    products = [p for p in store.list_products() if not p.purchased_at]
    log.info("추적 상품 %d개", len(products))
    n = 0
    for p in products:
        if process_product(store, p):
            n += 1
    log.info("완료 — 알림 %d건", n)
    return n
