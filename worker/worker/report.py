"""주간 요약 리포트 — `python -m worker report`. 사용자별로 지난 7일을 한 장으로: 알림 수, 지금 사도 되는 상품,
목표가 근접, 다가오는 세일, 절약액, 정품 리스크, 중단 상품. 텔레그램/이메일(설정대로) + 웹푸시 한 줄.
웹 lib/report.ts 의 weeklySummary 와 같은 항목·규칙 (앱 알림 탭 상단 카드)."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .baseline import compute_baseline
from .fx import krw_rates
from .models import Product
from .notify import KIND_LABEL, fmt_price, send_email, send_push, send_telegram
from .sales import upcoming_sales
from .storage import Storage

log = logging.getLogger(__name__)

TARGET_NEAR_PCT = 5.0      # 목표가까지 5% 이내면 '근접'
SALE_HORIZON_DAYS = 30
MAX_ITEMS = 5


@dataclass
class ReportItem:
    product: Product
    price: float
    baseline: Optional[float]
    pct: Optional[float]                 # 양수 = 평소보다 싸다
    target_gap_pct: Optional[float]      # (현재가-목표가)/목표가 %, 0 이하 = 이미 도달


@dataclass
class WeeklyReport:
    user_id: Optional[str]
    start: date
    end: date
    tracked: int
    alerts: Counter = field(default_factory=Counter)
    buy_now: list[ReportItem] = field(default_factory=list)
    target_near: list[ReportItem] = field(default_factory=list)
    sales: list[tuple[str, int, int]] = field(default_factory=list)   # (이름, D-day, 해당 상품 수)
    saved_krw: float = 0.0
    purchases: int = 0
    risk_high: list[Product] = field(default_factory=list)
    paused: list[Product] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.alerts or self.buy_now or self.target_near or self.purchases or self.risk_high or self.paused)


def _krw(v: float, currency: str, rates: dict[str, float]) -> float:
    return v if currency == "KRW" else v * rates.get(currency, 0.0)


def build_report(store: Storage, user_id: Optional[str], products: list[Product],
                 now: Optional[datetime] = None, rates: Optional[dict[str, float]] = None) -> WeeklyReport:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    us = store.settings_for(user_id)
    if rates is None:
        try:
            rates = krw_rates()
        except Exception:  # noqa: BLE001
            rates = {}
    rep = WeeklyReport(user_id, since.date(), now.date(), sum(1 for p in products if p.active and not p.purchased_at))

    rep.alerts = Counter(a.kind for a in store.alerts_since(user_id, since))

    sale_hits: Counter = Counter()
    sale_days: dict[str, int] = {}
    for p in products:
        if p.purchased_at:
            if p.purchased_at >= since:
                rep.purchases += 1
                hist = store.history(p.id, us.window_days)
                base = compute_baseline(hist, us.window_days, now) or p.purchased_price or 0.0
                rep.saved_krw += max(0.0, _krw(base - (p.purchased_price or 0.0), p.currency, rates))
            continue
        if not p.active:
            rep.paused.append(p)
            continue
        hist = store.history(p.id, us.window_days)
        if not hist or not hist[-1].in_stock or hist[-1].suspect:   # 웹 report.ts 와 동일: 최신 스냅샷이 품절·확인 대기면 신호 없음
            continue
        last = hist[-1]
        base = compute_baseline(hist, us.window_days, now)
        pct = round((base - last.price) / base * 100, 1) if base else None
        gap = round((last.price - p.target_price) / p.target_price * 100, 1) if p.target_price else None
        item = ReportItem(p, last.price, base, pct, gap)
        if p.risk_level == "high":
            rep.risk_high.append(p)
        elif (gap is not None and gap <= 0) or (pct is not None and pct >= us.threshold_pct):
            rep.buy_now.append(item)
        elif gap is not None and gap <= TARGET_NEAR_PCT:
            rep.target_near.append(item)
        for u in upcoming_sales(p.country, p.site, p.category or "전자", now.date(), SALE_HORIZON_DAYS):
            if u.strength >= 2:
                sale_hits[u.name] += 1
                sale_days[u.name] = u.days_until

    rep.buy_now.sort(key=lambda i: -(i.pct or 0))
    rep.target_near.sort(key=lambda i: i.target_gap_pct or 0)
    rep.sales = sorted(((n, sale_days[n], c) for n, c in sale_hits.items()), key=lambda t: t[1])
    return rep


def _dday(d: int) -> str:
    return "진행 중" if d == 0 else f"D-{d}"


def render_report(rep: WeeklyReport) -> tuple[str, str]:
    """(제목, 본문) — 텔레그램·이메일 공용 평문."""
    title = f"📋 주간 요약 {rep.start.month}/{rep.start.day}~{rep.end.month}/{rep.end.day}"
    lines: list[str] = []
    total = sum(rep.alerts.values())
    kinds = " · ".join(f"{KIND_LABEL.get(k, k)} {n}" for k, n in rep.alerts.most_common())
    lines.append(f"추적 {rep.tracked}개 · 이번 주 알림 {total}건" + (f" ({kinds})" if kinds else ""))

    if rep.buy_now:
        lines.append(f"\n✅ 지금 사도 됨 ({len(rep.buy_now)})")
        for i in rep.buy_now[:MAX_ITEMS]:
            why = "목표가 도달" if i.target_gap_pct is not None and i.target_gap_pct <= 0 else f"평소보다 {i.pct or 0:.0f}% 싸다"
            lines.append(f" • {i.product.title[:40]} — {fmt_price(i.price, i.product.currency)} ({why})")
        if len(rep.buy_now) > MAX_ITEMS:
            lines.append(f"   … 외 {len(rep.buy_now) - MAX_ITEMS}개")
    if rep.target_near:
        lines.append(f"\n🎯 목표가 근접 ({len(rep.target_near)})")
        for i in rep.target_near[:MAX_ITEMS]:
            lines.append(f" • {i.product.title[:40]} — {fmt_price(i.price, i.product.currency)} (목표가까지 {i.target_gap_pct or 0:.0f}%)")
    if rep.sales:
        lines.append(f"\n⏳ {SALE_HORIZON_DAYS}일 내 세일")
        for name, d, n in rep.sales[:MAX_ITEMS]:
            lines.append(f" • {name} {_dday(d)} — 상품 {n}개")
    if rep.purchases:
        lines.append(f"\n💰 이번 주 구매 {rep.purchases}건 · 절약 ≈ {fmt_price(rep.saved_krw, 'KRW')} (기준선 대비)")
    if rep.risk_high:
        lines.append(f"\n⚠ 정품 리스크 높음 {len(rep.risk_high)}개 — 판매자를 확인하세요")
        for p in rep.risk_high[:3]:
            lines.append(f" • {p.title[:40]}")
    if rep.paused:
        lines.append(f"\n⏸ 추적 중단 {len(rep.paused)}개 — 상세에서 재개하거나 북마클릿으로 기록하세요")
    if rep.empty:
        lines.append("\n조용한 한 주였습니다. 특별한 신호 없음.")
    return title, "\n".join(lines)


def push_line(rep: WeeklyReport) -> str:
    """웹푸시용 한 줄."""
    parts = [f"알림 {sum(rep.alerts.values())}건"]
    if rep.buy_now:
        parts.append(f"지금 사도 됨 {len(rep.buy_now)}개")
    if rep.sales:
        name, d, _ = rep.sales[0]
        parts.append(f"{name} {_dday(d)}")
    if rep.purchases:
        parts.append(f"절약 {fmt_price(rep.saved_krw, 'KRW')}")
    return " · ".join(parts)


def send_report(store: Storage, rep: WeeklyReport) -> list[str]:
    us = store.settings_for(rep.user_id)
    title, body = render_report(rep)
    sent: list[str] = []
    subs = store.push_subscriptions(rep.user_id)
    if us.notify_push and subs:
        expired = send_push(subs, title, push_line(rep), "/alerts")
        for ep in expired:
            store.remove_push_subscription(ep)
        if len(expired) < len(subs):
            sent.append("push")
    if us.notify_telegram and send_telegram(f"{title}\n{body}", us.telegram_chat_id):
        sent.append("telegram")
    if us.notify_email and send_email(title, body, us.email):
        sent.append("email")
    return sent


def run_weekly(store: Storage, dry_run: bool = False) -> int:
    """모든 사용자에게 주간 리포트. dry_run 이면 출력만. 발송한 사용자 수 반환."""
    products = store.list_products(active_only=False)
    by_user: dict[Optional[str], list[Product]] = {}
    for p in products:
        by_user.setdefault(p.user_id, []).append(p)
    n = 0
    for uid, plist in by_user.items():
        rep = build_report(store, uid, plist)
        if dry_run:
            title, body = render_report(rep)
            print(f"--- user={uid or 'local'}\n{title}\n{body}\n")
            continue
        sent = send_report(store, rep)
        log.info("주간 리포트 user=%s 발송=%s", uid or "local", sent or "채널 없음")
        n += 1 if sent else 0
    return n
