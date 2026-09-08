"""환율: 무료·키 불필요 open.er-api.com (일 1회 갱신). 실패 시 폴백 상수. 웹 lib/fx.ts 와 동일 소스."""
from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)

FALLBACK_KRW = {"USD": 1380.0, "CNY": 190.0, "EUR": 1500.0, "JPY": 9.3, "KRW": 1.0}  # 대략값 — 네트워크 실패 시만 사용
_cache: dict = {"at": 0.0, "rates": None}
TTL = 6 * 3600


def krw_rates() -> dict[str, float]:
    """통화 → 1단위당 KRW."""
    if _cache["rates"] and time.time() - _cache["at"] < TTL:
        return _cache["rates"]
    try:
        r = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        d = r.json()
        usd = d["rates"]
        krw_per_usd = float(usd["KRW"])
        rates = {cur: krw_per_usd / float(v) for cur, v in usd.items() if v}
        rates["USD"] = krw_per_usd
        rates["KRW"] = 1.0
        _cache.update(at=time.time(), rates=rates)
        return rates
    except Exception as e:  # noqa: BLE001
        log.debug("환율 조회 실패 %s → 폴백", e)
        return dict(FALLBACK_KRW)


def to_krw(amount: float, currency: str, rates: dict[str, float] | None = None) -> float:
    rates = rates or krw_rates()
    return amount * rates.get(currency.upper(), FALLBACK_KRW.get(currency.upper(), 1.0))
