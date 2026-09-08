"""v0.8: 세일 캘린더(워커 포팅)·추세 — 웹 sales.ts/trend.ts 와 같은 결과여야 한다."""
from datetime import date, datetime, timedelta, timezone

from worker.models import PriceSnapshot
from worker.sales import _black_friday, buy_timing, upcoming_sales
from worker.trend import trend_pct


def test_black_friday_dates():
    assert _black_friday(2026) == date(2026, 11, 27)
    assert _black_friday(2025) == date(2025, 11, 28)


def test_upcoming_kr_before_chuseok():
    up = upcoming_sales("KR", "coupang", "전자", today=date(2026, 9, 6))
    names = [u.name for u in up]
    assert "애플 신제품(9월)" in names and "추석 연휴 세일" in names
    assert up[0].days_until == 4 and up[0].name == "애플 신제품(9월)"
    assert next(u for u in up if u.name == "추석 연휴 세일").days_until == 19


def test_upcoming_dedup_and_in_progress():
    up = upcoming_sales("CN", "aliexpress", today=date(2026, 11, 12))
    assert up[0].name == "광군제 11·11" and up[0].days_until == 0
    assert len([u for u in up if u.name == "광군제 11·11"]) == 1


def test_upcoming_scope_filters_site():
    assert not any(u.name == "11절" for u in upcoming_sales("KR", "coupang", today=date(2026, 11, 1)))
    assert any(u.name == "11절" for u in upcoming_sales("KR", "11st", today=date(2026, 11, 1)))


def test_buy_timing_rules():
    up = upcoming_sales("US", "amazon", today=date(2026, 11, 1))
    assert buy_timing(True, up).verdict == "buy"
    t = buy_timing(False, up)
    assert t.verdict == "wait" and "블랙프라이데이" in t.label
    assert buy_timing(False, []).label == "45일 내 큰 세일 없음"
    weak_only = upcoming_sales("KR", "coupang", today=date(2026, 9, 6))
    assert buy_timing(False, weak_only).verdict == "neutral"


NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


def _snaps(prices):
    return [PriceSnapshot("p", v, "USD", "A", True, NOW - timedelta(days=len(prices) - i)) for i, v in enumerate(prices)]


def test_trend_pct_down_and_flat():
    down = trend_pct(_snaps([100, 98, 96, 94, 92, 90]), now=NOW)
    assert down is not None and down < -8
    flat = trend_pct(_snaps([100, 100, 100, 100, 100]), now=NOW)
    assert flat == 0.0
    assert trend_pct(_snaps([100, 90, 80]), now=NOW) is None   # 표본 4개 미만


def test_step_drop_is_not_a_trend():
    """평평하다 오늘 -24% 계단 → 추세 아님(None). 세일 급락에 "더 떨어지는 중" 이 붙으면 안 된다."""
    assert trend_pct(_snaps([130] * 8 + [99]), now=NOW) is None
    assert trend_pct(_snaps([130] * 8 + [99, 99]), now=NOW) is None
    noisy = trend_pct(_snaps([100, 101, 97, 98, 94, 95, 91, 92, 88]), now=NOW)   # 노이즈 섞인 완만한 하락은 추세
    assert noisy is not None and noisy < -8
