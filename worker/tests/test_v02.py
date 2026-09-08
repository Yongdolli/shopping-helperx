"""v0.2: 가짜 할인, 판매자 변경, 옵션 파싱, 쿠팡 서명, 어댑터 예산."""
from datetime import datetime, timedelta, timezone

import pytest

from worker.adapters.base import BudgetExceeded
from worker.adapters.coupang import pick_match, sign
from worker.adapters.mock import MockAdapter
from worker.baseline import claimed_discount_pct, is_fake_discount, judge
from worker.models import PriceSnapshot, Product, parse_variant

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def snaps(prices, seller="A", list_price=None):
    return [PriceSnapshot("p", p, "USD", seller, True, NOW - timedelta(days=len(prices) - i), list_price)
            for i, p in enumerate(prices)]


# ---- 가짜 할인
def test_claimed_discount():
    assert claimed_discount_pct(80, 100) == 20.0
    assert claimed_discount_pct(100, 100) is None
    assert claimed_discount_pct(100, None) is None


def test_fake_discount_when_price_is_usual():
    # 정가 800 표시, 실제 판매가는 늘 600 → 25% 할인 주장이지만 평소와 같음
    hist = snaps([600, 600, 600, 600], list_price=800)
    cur = PriceSnapshot("p", 600, "USD", "A", True, NOW, 800)
    v = judge(cur, hist)
    assert v.kind == "fake" and v.fake and v.claimed_pct == 25.0


def test_real_discount_is_not_fake():
    hist = snaps([600, 600, 600, 600], list_price=800)
    cur = PriceSnapshot("p", 500, "USD", "A", True, NOW, 800)
    v = judge(cur, hist)
    assert v.kind == "drop" and not v.fake


def test_small_claim_not_fake():
    assert not is_fake_discount(95, 100, 95)  # 5% 주장 → 무시


# ---- 판매자 변경
def test_seller_change_noted_but_drop_still_fires():
    hist = snaps([100, 100, 100, 100], seller="A")
    cur = PriceSnapshot("p", 85, "USD", "B", True, NOW)
    v = judge(cur, hist)
    assert v.kind == "drop" and v.seller_changed == "판매자 변경: A → B"


def test_same_seller_no_note():
    hist = snaps([100, 100, 100], seller="A")
    v = judge(PriceSnapshot("p", 100, "USD", "A", True, NOW), hist)
    assert v.seller_changed is None


# ---- 옵션 파싱
def test_parse_variant():
    assert parse_variant("https://www.coupang.com/vp/products/1?itemId=2&vendorItemId=3") == "vendorItemId=3&itemId=2"
    assert parse_variant("https://ko.aliexpress.com/item/1.html?sku_id=99") == "sku_id=99"
    assert parse_variant("https://www.ebay.com/itm/123?var=456") == "var=456"
    assert parse_variant("https://www.11st.co.kr/products/1") is None


# ---- 쿠팡
def test_coupang_signature_format():
    h = sign("GET", "/v2/x", "keyword=a&limit=1", "AK", "SK", now=datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc))
    assert h.startswith("CEA algorithm=HmacSHA256, access-key=AK, signed-date=260905T120000Z, signature=")
    assert len(h.split("signature=")[1]) == 64


def test_coupang_pick_match():
    items = [{"productId": 1, "productPrice": 10}, {"productId": 22, "productPrice": 20}]
    assert pick_match(items, "22")["productPrice"] == 20
    assert pick_match(items, "3") is None


# ---- 예산
def test_budget_exceeded():
    a = MockAdapter()
    a.budget_per_run = 2
    a.reset_budget()
    a.consume(); a.consume()
    with pytest.raises(BudgetExceeded):
        a.consume()


def test_mock_list_price_and_seller():
    a = MockAdapter()
    q = a.fetch(Product("x", "t", "mock://s/x?base=100&list=150&seller=Z", "mock", "US", "USD"))
    assert q.list_price == 150 and q.seller == "Z"
