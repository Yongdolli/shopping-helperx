from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass(frozen=True)
class Settings:
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_key: str = field(default_factory=lambda: _env("SUPABASE_SERVICE_KEY"))
    sqlite_path: Path = field(default_factory=lambda: ROOT / _env("SQLITE_PATH", "data/dev.db"))

    threshold_pct: float = field(default_factory=lambda: float(_env("THRESHOLD_PCT", "10")))
    window_days: int = field(default_factory=lambda: int(_env("WINDOW_DAYS", "90")))
    alert_cooldown_hours: int = 24
    digest: bool = field(default_factory=lambda: _env("DIGEST", "1") not in ("0", "false", "no"))  # SQLite 로컬 사용자 기본값

    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))

    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_pass: str = field(default_factory=lambda: _env("SMTP_PASS"))
    alert_email_to: str = field(default_factory=lambda: _env("ALERT_EMAIL_TO"))

    vapid_public_key: str = field(default_factory=lambda: _env("VAPID_PUBLIC_KEY"))
    vapid_private_key: str = field(default_factory=lambda: _env("VAPID_PRIVATE_KEY"))
    vapid_subject: str = field(default_factory=lambda: _env("VAPID_SUBJECT", "mailto:admin@example.com"))

    coupang_access_key: str = field(default_factory=lambda: _env("COUPANG_ACCESS_KEY"))
    coupang_secret_key: str = field(default_factory=lambda: _env("COUPANG_SECRET_KEY"))
    ebay_client_id: str = field(default_factory=lambda: _env("EBAY_CLIENT_ID"))
    ebay_client_secret: str = field(default_factory=lambda: _env("EBAY_CLIENT_SECRET"))
    bestbuy_api_key: str = field(default_factory=lambda: _env("BESTBUY_API_KEY"))
    elevenst_api_key: str = field(default_factory=lambda: _env("ELEVENST_API_KEY"))
    aliexpress_app_key: str = field(default_factory=lambda: _env("ALIEXPRESS_APP_KEY"))
    aliexpress_app_secret: str = field(default_factory=lambda: _env("ALIEXPRESS_APP_SECRET"))
    keepa_api_key: str = field(default_factory=lambda: _env("KEEPA_API_KEY"))

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 ShoppingHelper/0.1"
    )

    @property
    def use_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


settings = Settings()
