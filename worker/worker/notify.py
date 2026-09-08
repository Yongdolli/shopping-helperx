"""알림 발송: 웹푸시 · 텔레그램 · 이메일. 채널 추가 = 함수 하나 + dispatch 에 등록."""
from __future__ import annotations

import json
import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from .config import settings
from .fx import krw_rates
from .landed import landed_price
from .models import Alert, Product, PushSubscription, UserSettings

log = logging.getLogger(__name__)

KIND_LABEL = {"target": "목표가 도달", "drop": "가격 급락", "low": "역대 최저가", "restock": "재입고", "fake": "가짜 할인 의심", "paused": "추적 자동 중단"}


def fmt_price(v: float, currency: str) -> str:
    if currency == "KRW":
        return f"{v:,.0f}원"
    sym = {"USD": "$", "CNY": "¥", "EUR": "€", "JPY": "¥"}.get(currency, currency + " ")
    return f"{sym}{v:,.2f}"


def render(alert: Alert, product: Product) -> tuple[str, str]:
    """(제목, 본문)"""
    title = f"[{KIND_LABEL.get(alert.kind, alert.kind)}] {product.title}"
    lines = [f"현재가: {fmt_price(alert.price, product.currency)}"]
    if product.currency != "KRW" and alert.price:
        try:
            l = landed_price(alert.price, product.currency, product.site, krw_rates(), product.category or "전자")
            lines.append(f"≈ 최종가 {l.total_krw:,.0f}원 (환율·배송·세금 추정, {l.note})")
        except Exception:  # noqa: BLE001
            pass
    if alert.baseline and alert.pct is not None:
        lines.append(f"기준선: {fmt_price(alert.baseline, product.currency)}  (▼{alert.pct:.1f}%)")
    if product.variant:
        lines.append(f"옵션: {product.variant}")
    if alert.note:
        lines.append(f"⚠ {alert.note}")
    lines.append(f"{product.site} · {product.url}")
    return title, "\n".join(lines)


# ---------------------------------------------------------------- Web Push
def send_push(subs: list[PushSubscription], title: str, body: str, url: str) -> list[str]:
    """각 구독에 발송. 410/404(만료) 구독 endpoint 목록을 돌려준다 → 호출자가 삭제."""
    if not (settings.vapid_private_key and subs):
        return []
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        log.warning("pywebpush 미설치 — pip install pywebpush")
        return []
    expired: list[str] = []
    payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
    for s in subs:
        try:
            webpush(
                subscription_info={"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=3600,
            )
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):
                expired.append(s.endpoint)
            else:
                log.warning("push 실패 %s %s", code, str(e)[:120])
    return expired


# ---------------------------------------------------------------- Telegram / Email
def send_telegram(text: str, chat_id: str | None = None) -> bool:
    token, chat = settings.telegram_bot_token, chat_id or settings.telegram_chat_id
    if not token or not chat:
        return False
    r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat, "text": text, "disable_web_page_preview": False}, timeout=15)
    if r.status_code != 200:
        log.warning("telegram 실패 %s %s", r.status_code, r.text[:120])
        return False
    return True


def send_email(subject: str, body: str, to: str | None = None) -> bool:
    to = to or settings.alert_email_to
    if not (settings.smtp_host and settings.smtp_user and to):
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, settings.smtp_user, to
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass)
            s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("email 실패 %s", e)
        return False


def dispatch(alert: Alert, product: Product, us: UserSettings, subs: list[PushSubscription]) -> tuple[list[str], list[str]]:
    """설정에 따라 채널별 발송. (성공 채널 목록, 만료된 push endpoint 목록) 반환."""
    title, body = render(alert, product)
    sent: list[str] = []
    expired: list[str] = []
    if us.notify_push and subs:
        expired = send_push(subs, title, body, f"/p/{product.id}")
        if len(expired) < len(subs):
            sent.append("push")
    if us.notify_telegram and send_telegram(f"{title}\n{body}", us.telegram_chat_id):
        sent.append("telegram")
    if us.notify_email and send_email(title, body, us.email):
        sent.append("email")
    return sent, expired
