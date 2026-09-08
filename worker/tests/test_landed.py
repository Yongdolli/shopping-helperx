from worker.landed import landed_price, origin_of

RATES = {"USD": 1400.0, "CNY": 195.0, "KRW": 1.0}


def test_domestic_passthrough():
    l = landed_price(449000, "KRW", "coupang", RATES)
    assert l.total_krw == 449000 and l.duty_free and l.note == "국내"


def test_us_under_200_duty_free():
    l = landed_price(159.99, "USD", "amazon", RATES, "전자")
    assert l.duty_free and l.total_krw == round(159.99 * 1400 + 18 * 1400)


def test_us_over_200_electronics_zero_duty_but_vat():
    l = landed_price(599, "USD", "bestbuy", RATES, "전자")
    assert not l.duty_free
    goods, ship = 599 * 1400, 18 * 1400
    assert l.total_krw == round((goods + ship) * 1.10)      # 관세 0%, 부가세 10%
    assert any("부가세" in k for k, _ in l.lines) and not any(v for k, v in l.lines if k.startswith("관세") and v)


def test_cn_over_150_clothing_duty():
    l = landed_price(1200, "CNY", "taobao", RATES, "의류")   # ≈ $167 > $150
    assert not l.duty_free
    goods, ship = 1200 * 195, 2 * 1400
    duty = (goods + ship) * 0.13
    assert l.total_krw == round(goods + ship + duty + (goods + ship + duty) * 0.10)


def test_origin():
    assert origin_of("ebay") == "US" and origin_of("temu") == "CN" and origin_of("11st") == "KR"
