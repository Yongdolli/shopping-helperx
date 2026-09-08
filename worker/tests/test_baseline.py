from datetime import datetime, timedelta, timezone

from worker.baseline import compute_baseline, judge
from worker.models import PriceSnapshot

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def snaps(prices, days_ago_start=30, in_stock=True):
    out = []
    for i, p in enumerate(prices):
        out.append(PriceSnapshot("p", p, "KRW", None, in_stock, NOW - timedelta(days=days_ago_start - i)))
    return out


def test_baseline_is_median_not_mean():
    # 가짜 할인: 하루만 정가 부풀림 → 평균은 오르지만 중앙값은 그대로
    hist = snaps([100, 100, 100, 100, 300])
    assert compute_baseline(hist, 90, NOW) == 100


def test_baseline_needs_min_samples():
    assert compute_baseline(snaps([100, 100]), 90, NOW) is None


def test_baseline_ignores_out_of_window():
    old = snaps([50, 50, 50], days_ago_start=200)
    recent = snaps([100, 100, 100])
    assert compute_baseline(old + recent, 90, NOW) == 100


def test_drop_triggers_at_threshold():
    hist = snaps([100, 100, 100, 100])
    cur = PriceSnapshot("p", 90, "KRW", None, True, NOW)
    v = judge(cur, hist, threshold_pct=10)
    assert v.kind == "drop" and v.pct == 10.0


def test_no_drop_above_threshold():
    hist = snaps([100, 90, 100, 100])  # 90 이 있으므로 91 은 역대 최저도 아님
    cur = PriceSnapshot("p", 91, "KRW", None, True, NOW)
    assert judge(cur, hist, threshold_pct=10).kind is None


def test_all_time_low_without_drop():
    hist = snaps([100, 95, 100, 98])
    cur = PriceSnapshot("p", 94, "KRW", None, True, NOW)
    assert judge(cur, hist, threshold_pct=10).kind == "low"


def test_restock():
    hist = snaps([100, 100, 100]) + [PriceSnapshot("p", 100, "KRW", None, False, NOW - timedelta(hours=1))]
    cur = PriceSnapshot("p", 100, "KRW", None, True, NOW)
    assert judge(cur, hist).kind == "restock"


def test_out_of_stock_never_alerts():
    hist = snaps([100, 100, 100, 100])
    cur = PriceSnapshot("p", 50, "KRW", None, False, NOW)
    assert judge(cur, hist).kind is None
