from datetime import datetime, timedelta, timezone

from worker.baseline import judge
from worker.decision import decide
from worker.models import PriceSnapshot

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)
HIST = [PriceSnapshot("p", 100, "USD", "A", True, NOW - timedelta(days=4 - i)) for i in range(4)]


def test_target_has_priority_over_drop():
    v = judge(PriceSnapshot("p", 80, "USD", "A", True, NOW), HIST, 10, 90, target_price=85)
    assert v.kind == "target"


def test_target_not_hit_falls_back():
    v = judge(PriceSnapshot("p", 88, "USD", "A", True, NOW), HIST, 10, 90, target_price=85)
    assert v.kind == "drop"


def test_decide_buy():
    d = decide(12, 10, "low")
    assert d.verdict == "buy" and "12%" in d.text


def test_decide_avoid_on_high_risk():
    assert decide(40, 10, "high").verdict == "avoid"


def test_decide_wait_when_falling():
    assert decide(12, 10, "low", trend_pct=-10).verdict == "wait"


def test_decide_fake_neutral():
    d = decide(0, 10, "low", fake=True)
    assert d.verdict == "neutral" and "가짜" in d.text


def test_decide_wait_for_sale():
    assert decide(2, 10, "low", wait_label="20일 뒤 블랙프라이데이").verdict == "wait"
