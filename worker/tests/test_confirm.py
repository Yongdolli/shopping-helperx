from datetime import datetime, timedelta, timezone

from worker.baseline import compute_baseline, needs_confirmation
from worker.models import PriceSnapshot

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def snaps(prices, suspect_last=False):
    out = [PriceSnapshot("p", p, "USD", "A", True, NOW - timedelta(days=len(prices) - i)) for i, p in enumerate(prices)]
    if suspect_last:
        out[-1].suspect = True
    return out


def test_extreme_first_time_needs_confirmation():
    hist = snaps([100, 100, 100, 100])
    cur = PriceSnapshot("p", 10, "USD", "A", True, NOW)   # 파싱 오류로 1/10
    assert needs_confirmation(cur, hist, compute_baseline(hist, 90, NOW))


def test_extreme_confirmed_when_repeated():
    hist = snaps([100, 100, 100, 100, 55], suspect_last=True)   # 직전에 -45% 를 suspect 로 기록
    cur = PriceSnapshot("p", 54, "USD", "A", True, NOW)
    assert not needs_confirmation(cur, hist, compute_baseline(hist, 90, NOW))


def test_suspect_excluded_from_baseline():
    hist = snaps([100, 100, 100, 10], suspect_last=True)
    assert compute_baseline(hist, 90, NOW) == 100


def test_normal_drop_no_confirmation():
    hist = snaps([100, 100, 100, 100])
    cur = PriceSnapshot("p", 85, "USD", "A", True, NOW)  # -15% 는 바로 알림
    assert not needs_confirmation(cur, hist, compute_baseline(hist, 90, NOW))
