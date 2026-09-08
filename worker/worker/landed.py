"""크로스보더 실구매가(최종가) 추정. 순수 함수 — 웹 lib/landed.ts 와 규칙 동일.

한국 소비자 기준. 해외 사이트 가격을 원화로 환산하고 배송비·관세·부가세를 얹는다.
- 면세 한도(물품가 기준): 미국발 200 USD (한미 FTA 목록통관), 그 외 150 USD.
- 한도 초과 시: 관세 = 과세가격(물품가+배송비) × 카테고리 관세율, 부가세 = (과세가격+관세) × 10%.
- 관세율은 단순화한 대표값(정확한 세율은 HS코드에 따라 다름 — UI 에 '추정' 표기).
"""
from __future__ import annotations

from dataclasses import dataclass, field

US_SITES = {"amazon", "ebay", "walmart", "bestbuy", "target", "etsy"}
CN_SITES = {"aliexpress", "temu", "shein", "taobao", "tmall", "jd", "1688"}

DUTY_FREE_USD = {"US": 200.0, "OTHER": 150.0}
# 카테고리별 (관세율, 기본 배송비 USD: 미국발 / 중국발)
CATEGORY = {
    "전자": (0.0, 18.0, 0.0),      # ITA 협정 → 무관세. 미국 배대지 평균 $18, 알리/테무 무료배송 가정
    "의류": (0.13, 15.0, 2.0),
    "신발": (0.13, 18.0, 3.0),
    "화장품": (0.065, 12.0, 2.0),   # 한미 FTA 0%, 중국발 6.5% 의 중간값
    "식품": (0.30, 25.0, 5.0),
    "장난감": (0.08, 15.0, 2.0),
    "가방": (0.08, 15.0, 3.0),
    "기타": (0.08, 15.0, 3.0),
}
VAT = 0.10


@dataclass
class Landed:
    total_krw: float
    lines: list[tuple[str, float]] = field(default_factory=list)  # (항목, KRW)
    duty_free: bool = True
    note: str = ""


def origin_of(site: str) -> str:
    if site in US_SITES:
        return "US"
    if site in CN_SITES:
        return "CN"
    return "KR"


def landed_price(price: float, currency: str, site: str, rates: dict[str, float], category: str = "전자",
                 shipping_override: float | None = None) -> Landed:
    """rates: 통화 → KRW. 국내 사이트는 그대로."""
    origin = origin_of(site)
    if origin == "KR" or currency.upper() == "KRW" and origin == "KR":
        return Landed(price, [("상품가", price)], True, "국내")

    rate = rates.get(currency.upper(), 1.0)
    usd_rate = rates.get("USD", 1380.0)
    goods_krw = price * rate
    goods_usd = goods_krw / usd_rate
    duty_rate, ship_us, ship_cn = CATEGORY.get(category, CATEGORY["기타"])
    ship_usd = shipping_override if shipping_override is not None else (ship_us if origin == "US" else ship_cn)
    ship_krw = ship_usd * usd_rate
    limit = DUTY_FREE_USD["US"] if origin == "US" else DUTY_FREE_USD["OTHER"]

    lines = [("상품가", round(goods_krw)), ("배송비(추정)", round(ship_krw))]
    if goods_usd <= limit:
        total = goods_krw + ship_krw
        return Landed(round(total), lines, True, f"면세 (물품가 ${goods_usd:,.0f} ≤ ${limit:,.0f})")
    taxable = goods_krw + ship_krw
    duty = taxable * duty_rate
    vat = (taxable + duty) * VAT
    lines += [(f"관세 {duty_rate*100:.1f}%", round(duty)), ("부가세 10%", round(vat))]
    return Landed(round(taxable + duty + vat), lines, False, f"면세 한도 초과 (물품가 ${goods_usd:,.0f} > ${limit:,.0f})")
