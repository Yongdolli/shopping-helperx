"""하루 3회 다이제스트 — `python -m worker digest`. 설정 `digest=True`(기본) 인 사용자는 수집 시점에 알림을 저장만 하고(notified=False),
아침 08:00 · 점심 12:30 · 저녁 19:00 KST 에 이 명령이 모아서 한 번에 보낸다. 새 알림이 없으면 아무것도 보내지 않는다.
`digest=False` 면 run.py 가 감지 즉시 발송(기존 동작)."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from .deals import fmt_deal, matches_keywords, pick_for_digest, same_key
from .models import Alert, Deal, Product
from .notify import KIND_LABEL, render, send_email, send_push, send_telegram
from .storage import Storage

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
KIND_ORDER = ["target", "drop", "low", "restock", "fake", "paused"]
MAX_PER_KIND = 8
SLOT_GAP_HOURS = 6.5
INSTANT_PCT = 20.0      # 관심 키워드 딜이 평소보다 이만큼 싸면 즉시
INSTANT_ANY_PCT = 40.0  # 키워드와 상관없이 평소보다 이만큼 싸면 즉시   # 012 전 대체 창 (08:00→12:30 4.5h, 12:30→19:00 6.5h)


def slot_label(now: Optional[datetime] = None) -> str:
    h = (now or datetime.now(timezone.utc)).astimezone(KST).hour
    return "🌅 아침 알림" if h < 11 else "☀️ 점심 알림" if h < 16 else "🌙 저녁 알림"


def render_digest(alerts: list[Alert], products: dict[str, Product], now: Optional[datetime] = None,
                  picks: Optional[list[tuple[Deal, str]]] = None) -> tuple[str, str, str]:
    """(제목, 본문, 푸시 한 줄). 종류 우선순위 순으로 묶고, 같은 상품은 최신 1건만. picks = 딜 피드에서 고른 (딜, 이유)."""
    picks = picks or []
    latest: dict[tuple[str, str], Alert] = {}
    for a in sorted(alerts, key=lambda a: a.created_at):
        latest[(a.product_id, a.kind)] = a
    items = list(latest.values())
    counts = Counter(a.kind for a in items)
    head = [f"새 알림 {len(items)}건"] if items else []
    if picks:
        head.append(f"딜 {len(picks)}건")
    title = f"{slot_label(now)} — " + " · ".join(head)
    summary = " · ".join([f"{KIND_LABEL.get(k, k)} {counts[k]}" for k in KIND_ORDER if counts[k]] + ([f"🔥 딜 {len(picks)}"] if picks else []))

    lines = [summary]
    for kind in KIND_ORDER:
        group = [a for a in items if a.kind == kind]
        if not group:
            continue
        group.sort(key=lambda a: -(a.pct or 0))
        lines.append(f"\n[{KIND_LABEL.get(kind, kind)}]")
        for a in group[:MAX_PER_KIND]:
            p = products.get(a.product_id)
            if not p:
                continue
            _, body = render(a, p)
            lines.append(f"• {p.title[:48]}")
            lines.extend("   " + ln for ln in body.splitlines())
        if len(group) > MAX_PER_KIND:
            lines.append(f"   … 외 {len(group) - MAX_PER_KIND}건")
    if picks:
        lines.append("\n[🔥 딜] 핫딜 커뮤니티에서 고른 것 — 표시 할인율이라 정가 부풀리기가 섞일 수 있음")
        for d, why in picks:
            lines.append(f"• {fmt_deal(d)} · {why}")
            lines.append(f"   {d.url}")
    lines.append("\n앱 알림 탭에서 전체를 볼 수 있습니다. 즉시 알림으로 바꾸려면 설정 → '하루 3회 모아 받기' 를 끄세요.")
    return title, "\n".join(lines), summary


def run_digest(store: Storage, dry_run: bool = False, now: Optional[datetime] = None) -> int:
    """대기 중(notified=False) 알림을 사용자별로 모아 발송하고 notified 처리. 발송한 사용자 수 반환."""
    products = {p.id: p for p in store.list_products(active_only=False)}
    by_user: dict[Optional[str], list[Product]] = {}
    for p in products.values():
        by_user.setdefault(p.user_id, []).append(p)
    now_ = now or datetime.now(timezone.utc)
    # 최근 24시간 딜 중 아직 이 사용자에게 안 보낸 것 (창 겹침·구멍 없음, 늦게 시세 확인된 딜도 다음 슬롯에 포함).
    # 보낸 기록(012)이 없으면 직전 슬롯 간격(최대 13시간)으로 대체.
    recent_deals = store.list_deals(now_ - timedelta(hours=24))
    n = 0
    for uid in by_user:
        pending = store.pending_alerts(uid)
        us = store.settings_for(uid)
        keywords = [k for k in (us.deal_keywords or "").split(",") if k.strip()]
        sent_keys = store.sent_deal_keys(uid, now_ - timedelta(days=3))
        pool = ([d for d in recent_deals if same_key(d) not in sent_keys] if sent_keys is not None
                else [d for d in recent_deals if d.posted_at >= now_ - timedelta(hours=SLOT_GAP_HOURS)])
        picks = pick_for_digest(pool, keywords, us.deal_min_pct)
        if not pending and not picks:
            continue
        title, body, line = render_digest(pending, products, now, picks)
        if dry_run:
            print(f"--- user={uid or 'local'}\n{title}\n{body}\n")
            continue
        sent: list[str] = []
        subs = store.push_subscriptions(uid)
        if us.notify_push and subs:
            expired = send_push(subs, title, line, "/alerts")
            for ep in expired:
                store.remove_push_subscription(ep)
            if len(expired) < len(subs):
                sent.append("push")
        if us.notify_telegram and send_telegram(f"{title}\n{body}", us.telegram_chat_id):
            sent.append("telegram")
        if us.notify_email and send_email(title, body, us.email):
            sent.append("email")
        store.mark_notified([a.id for a in pending if a.id is not None])
        store.mark_deals_sent(uid, [same_key(d) for d, _ in picks])
        log.info("다이제스트 user=%s 알림 %d건·딜 %d건 발송=%s", uid or "local", len(pending), len(picks), sent or "채널 없음(앱 내)")
        n += 1
    return n



def instant_deal_alerts(store: Storage, now: Optional[datetime] = None) -> int:
    """큰 딜은 다이제스트를 기다리지 않고 바로: 시세로 확인된(평소 대비) 딜 중 끝나지 않은 것이
    관심 키워드 + 평소보다 INSTANT_PCT% 이상, 또는 키워드 무관 INSTANT_ANY_PCT% 이상이면 발송. 보낸 딜은 deal_sends 에 기록(다이제스트 중복 없음).
    보낸 기록(012)이 없으면 중복 위험이 있어 보내지 않는다. 발송 건수 반환."""
    now = now or datetime.now(timezone.utc)
    recent = [d for d in store.list_deals(now - timedelta(hours=12)) if d.below_pct is not None and not d.ended and d.price]
    if not recent:
        return 0
    users = {p.user_id for p in store.list_products(active_only=False)}
    total = 0
    for uid in users:
        sent_keys = store.sent_deal_keys(uid, now - timedelta(days=3))
        if sent_keys is None:
            continue
        us = store.settings_for(uid)
        keywords = [k for k in (us.deal_keywords or "").split(",") if k.strip()]
        picks, seen = [], set()
        for d in sorted(recent, key=lambda d: -(d.below_pct or 0)):
            k = same_key(d)
            if k in sent_keys or k in seen:
                continue
            kw = matches_keywords(d.title, keywords)
            if (kw and d.below_pct >= max(INSTANT_PCT, us.deal_min_pct)) or d.below_pct >= INSTANT_ANY_PCT:
                picks.append((d, f"관심 키워드 '{kw}'" if kw else "평소보다 크게 쌈")); seen.add(k)
        if not picks:
            continue
        picks = picks[:3]
        title = f"🔥 평소보다 {picks[0][0].below_pct:.0f}% 싼 딜" + (f" 외 {len(picks) - 1}건" if len(picks) > 1 else "")
        body = "\n".join(f"• {fmt_deal(d)} · {why}\n   {d.shop_url or d.url}" for d, why in picks)
        sent: list[str] = []
        subs = store.push_subscriptions(uid)
        if us.notify_push and subs:
            expired = send_push(subs, title, fmt_deal(picks[0][0]), "/deals")
            for ep in expired:
                store.remove_push_subscription(ep)
            if len(expired) < len(subs):
                sent.append("push")
        if us.notify_telegram and send_telegram(f"{title}\n{body}", us.telegram_chat_id):
            sent.append("telegram")
        if us.notify_email and send_email(title, body, us.email):
            sent.append("email")
        if sent:                                    # 채널이 없으면 기록하지 않음 → 다이제스트·앱에서 보게 됨
            store.mark_deals_sent(uid, [same_key(d) for d, _ in picks])
            total += len(picks)
            log.info("즉시 딜 알림 user=%s %d건 발송=%s", uid or "local", len(picks), sent)
    return total
