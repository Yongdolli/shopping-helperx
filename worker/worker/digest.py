"""하루 3회 다이제스트 — `python -m worker digest`. 설정 `digest=True`(기본) 인 사용자는 수집 시점에 알림을 저장만 하고(notified=False),
아침 08:00 · 점심 12:30 · 저녁 19:00 KST 에 이 명령이 모아서 한 번에 보낸다. 새 알림이 없으면 아무것도 보내지 않는다.
`digest=False` 면 run.py 가 감지 즉시 발송(기존 동작)."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import Alert, Product
from .notify import KIND_LABEL, render, send_email, send_push, send_telegram
from .storage import Storage

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
KIND_ORDER = ["target", "drop", "low", "restock", "fake", "paused"]
MAX_PER_KIND = 8


def slot_label(now: Optional[datetime] = None) -> str:
    h = (now or datetime.now(timezone.utc)).astimezone(KST).hour
    return "🌅 아침 알림" if h < 11 else "☀️ 점심 알림" if h < 16 else "🌙 저녁 알림"


def render_digest(alerts: list[Alert], products: dict[str, Product], now: Optional[datetime] = None) -> tuple[str, str, str]:
    """(제목, 본문, 푸시 한 줄). 종류 우선순위 순으로 묶고, 같은 상품은 최신 1건만."""
    latest: dict[tuple[str, str], Alert] = {}
    for a in sorted(alerts, key=lambda a: a.created_at):
        latest[(a.product_id, a.kind)] = a
    items = list(latest.values())
    counts = Counter(a.kind for a in items)
    title = f"{slot_label(now)} — 새 알림 {len(items)}건"
    summary = " · ".join(f"{KIND_LABEL.get(k, k)} {counts[k]}" for k in KIND_ORDER if counts[k])

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
    lines.append("\n앱 알림 탭에서 전체를 볼 수 있습니다. 즉시 알림으로 바꾸려면 설정 → '하루 3회 모아 받기' 를 끄세요.")
    return title, "\n".join(lines), summary


def run_digest(store: Storage, dry_run: bool = False, now: Optional[datetime] = None) -> int:
    """대기 중(notified=False) 알림을 사용자별로 모아 발송하고 notified 처리. 발송한 사용자 수 반환."""
    products = {p.id: p for p in store.list_products(active_only=False)}
    by_user: dict[Optional[str], list[Product]] = {}
    for p in products.values():
        by_user.setdefault(p.user_id, []).append(p)
    n = 0
    for uid in by_user:
        pending = store.pending_alerts(uid)
        if not pending:
            continue
        us = store.settings_for(uid)
        title, body, line = render_digest(pending, products, now)
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
        log.info("다이제스트 user=%s %d건 발송=%s", uid or "local", len(pending), sent or "채널 없음(앱 내)")
        n += 1
    return n

