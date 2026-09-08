from worker.risk import assess_risk, guess_model_no, is_official_seller


def test_strong_keyword_is_high():
    r = assess_risk("소니 WH-1000XM6 S급 미러급 헤드폰", "11st", 89000, seller="해외셀러")
    assert r.level == "high" and any("제목에" in x for x in r.reasons)


def test_price_outlier_cross_model_high():
    r = assess_risk("소니 WH-1000XM6", "11st", 89000, seller="어떤셀러", cross_baseline=449000, model_no="WH-1000XM6")
    assert r.level == "high" and any("다른 판매처 대비" in x for x in r.reasons)


def test_official_seller_lowers():
    r = assess_risk("소니 WH-1000XM6", "coupang", 400000, seller="쿠팡 로켓", baseline=449000, model_no="WH-1000XM6")
    assert r.level == "low"


def test_official_to_third_party_switch():
    r = assess_risk("소니 WH-1000XM6", "coupang", 300000, seller="제3자 판매자", usual_seller="쿠팡 로켓", baseline=449000, model_no="WH-1000XM6")
    assert r.level in ("medium", "high") and any("제3자" in x for x in r.reasons)


def test_verified_overrides():
    r = assess_risk("레플리카 명품 가방", "aliexpress", 10, verified=True)
    assert r.level == "low" and r.score == 0


def test_overseas_market_and_weak_word_medium():
    r = assess_risk("에어팟 프로 호환 케이스", "aliexpress", 3.0, seller="Shop123")
    assert r.level == "medium"


def test_normal_is_low():
    r = assess_risk("Kindle Paperwhite 16GB (2024)", "amazon", 159.99, seller="Amazon.com", baseline=155)
    assert r.level == "low"


def test_helpers():
    assert is_official_seller("브랜드공식스토어", "naver")
    assert is_official_seller(None, "bestbuy")
    assert not is_official_seller("길동상회", "coupang")
    assert guess_model_no("소니 WH-1000XM6 노이즈캔슬링") == "WH-1000XM6"
    assert guess_model_no("LG 올레드 evo C5 65인치 OLED65C5") == "OLED65C5"
    assert guess_model_no("Logitech MX Master 4 Mouse") is None


# ---- v0.8 판매자 이력 신호
def test_seller_churn_raises_risk():
    calm = assess_risk("소니 WH-1000XM6", "11st", 400000, seller="셀러A", baseline=410000, model_no="WH-1000XM6")
    churn = assess_risk("소니 WH-1000XM6", "11st", 400000, seller="셀러A", baseline=410000, model_no="WH-1000XM6", seller_changes=3)
    heavy = assess_risk("소니 WH-1000XM6", "11st", 400000, seller="셀러A", baseline=410000, model_no="WH-1000XM6", seller_changes=6)
    assert churn.score == calm.score + 15 and heavy.score == calm.score + 25
    assert any("판매자가 자주 바뀜 (90일 6회)" in x for x in heavy.reasons)


def test_seller_churn_ignored_for_official():
    r = assess_risk("소니 WH-1000XM6", "coupang", 400000, seller="쿠팡 로켓", baseline=410000, model_no="WH-1000XM6", seller_changes=6)
    assert r.level == "low" and not any("자주 바뀜" in x for x in r.reasons)


def test_seller_changes_counts_transitions():
    from datetime import datetime, timedelta, timezone
    from worker.baseline import seller_changes
    from worker.models import PriceSnapshot
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    sellers = ["A", "A", "B", "A", None, "C", "C", "A"]
    snaps = [PriceSnapshot("p", 100, "KRW", s, True, now - timedelta(days=len(sellers) - i)) for i, s in enumerate(sellers)]
    assert seller_changes(snaps, 90, now) == 4          # A→B, B→A, A→C, C→A (None 무시)
    assert seller_changes(snaps, 2, now) == 1           # 최근 2일: C, A
