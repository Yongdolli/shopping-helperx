"""`python -m worker doctor` — 키를 연결할 때 무엇이 켜졌고 무엇이 빠졌는지 한 번에 점검."""
from __future__ import annotations

import sys

from .adapters import ADAPTERS
from .config import settings


def _row(ok: bool | None, label: str, detail: str = "") -> str:
    mark = "✅" if ok else ("⚠️ " if ok is None else "❌")
    return f"  {mark} {label}" + (f" — {detail}" if detail else "")


def run_doctor() -> int:
    lines: list[str] = []
    problems = 0

    # 저장소
    lines.append("저장소")
    if settings.use_supabase:
        try:
            from .storage import SupabaseStorage
            st = SupabaseStorage(settings.supabase_url, settings.supabase_key)
            n = len(st.list_products(active_only=False))
            lines.append(_row(True, "Supabase 연결", f"products {n}개"))
            try:
                st.db.table("push_subscriptions").select("endpoint").limit(1).execute()
                st.db.table("products").select("target_price,tags,purchased_at,category,risk_level").limit(1).execute()
                st.db.table("user_settings").select("digest").limit(1).execute()
                st.db.table("products").select("variant_key").limit(1).execute()
                st.db.table("shares").select("token").limit(1).execute()
                lines.append(_row(True, "마이그레이션 001~009 적용됨"))
            except Exception as e:  # noqa: BLE001
                problems += 1
                lines.append(_row(False, "마이그레이션 누락", f"supabase/migrations/*.sql 을 순서대로 실행하세요 ({str(e)[:80]})"))
        except Exception as e:  # noqa: BLE001
            problems += 1
            lines.append(_row(False, "Supabase 연결 실패", str(e)[:100]))
    else:
        lines.append(_row(None, "Supabase 미설정 → SQLite 개발 모드", str(settings.sqlite_path)))

    # 알림 채널
    lines.append("알림 채널")
    lines.append(_row(bool(settings.vapid_private_key and settings.vapid_public_key), "웹푸시 VAPID", "python -m worker vapid 로 생성 후 .env 에 등록" if not settings.vapid_private_key else "설정됨"))
    if settings.vapid_private_key:
        try:
            import pywebpush  # noqa: F401
            lines.append(_row(True, "pywebpush 설치됨"))
        except ImportError:
            problems += 1
            lines.append(_row(False, "pywebpush 미설치", "pip install pywebpush"))
    lines.append(_row(bool(settings.telegram_bot_token and settings.telegram_chat_id), "텔레그램", "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID" if not settings.telegram_bot_token else "설정됨"))
    if settings.telegram_bot_token:
        try:
            import httpx
            r = httpx.get(f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe", timeout=10)
            ok = r.status_code == 200 and r.json().get("ok")
            lines.append(_row(bool(ok), "텔레그램 봇 토큰 유효", r.json().get("result", {}).get("username", "") if ok else r.text[:80]))
        except Exception as e:  # noqa: BLE001
            lines.append(_row(None, "텔레그램 확인 실패", str(e)[:80]))
    lines.append(_row(bool(settings.smtp_host and settings.smtp_user and settings.alert_email_to), "이메일(SMTP)", "선택" if not settings.smtp_host else "설정됨"))

    # 어댑터
    lines.append("사이트 어댑터 (available = 키 있음)")
    for a in ADAPTERS:
        if a.site in ("mock",):
            continue
        avail = a.available()
        hint = {
            "coupang": "COUPANG_ACCESS_KEY/SECRET_KEY (파트너스)", "ebay": "EBAY_CLIENT_ID/SECRET", "bestbuy": "BESTBUY_API_KEY",
            "11st": "ELEVENST_API_KEY", "aliexpress": "ALIEXPRESS_APP_KEY/SECRET",
        }.get(a.site, "키 불필요")
        lines.append(_row(True if avail else None, f"{a.site:<12}", ("활성" if avail else f"비활성 → {hint}") + (f" · {a.min_interval_hours}h 간격" if a.min_interval_hours else "")))

    # 환율
    lines.append("환율")
    try:
        from .fx import krw_rates
        r = krw_rates()
        live = r.get("USD") not in (None, 1380.0)
        lines.append(_row(True if live else None, "open.er-api.com", f"USD→KRW {r.get('USD'):,.0f}" + ("" if live else " (폴백 상수 — 네트워크 확인)")))
    except Exception as e:  # noqa: BLE001
        lines.append(_row(None, "환율 조회 실패", str(e)[:80]))

    print("\n".join(lines))
    print(f"\n{'문제 없음' if problems == 0 else f'문제 {problems}건'} — 키를 넣은 뒤 다시 실행하면 어댑터가 활성으로 바뀝니다.")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(run_doctor())
