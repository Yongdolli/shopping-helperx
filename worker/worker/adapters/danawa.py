"""다나와 상품 페이지 어댑터 — 국내 여러 몰의 최저가가 한 페이지에 모여 있어 국내 데이터의 핵심 소스.

주의: 실제 페이지 구조를 이 환경에서 확인하지 못해 **미검증**. 층층이 폴백:
  1) JSON-LD Product/Offer (있으면 가장 정확)
  2) 페이지 내 "최저가" 블록의 숫자 + 판매처명 (정규식)
  3) OpenGraph
실패하면 fail_count 가 쌓이고 10회 후 자동 중단 → 북마클릿으로 전환. robots.txt 준수, 12시간 간격.
"""
from __future__ import annotations

import re
from typing import Optional

from ..models import Product, Quote
from ..robots import allowed
from .base import AdapterError, BaseAdapter
from .jsonld import extract_from_html

PCODE_RE = re.compile(r"[?&]pcode=(\d+)")
# 최저가 블록 후보: <em class="prc_c">1,234,000</em> / class="lwst_prc" ... / "lowestPrice":1234000
PRICE_PATTERNS = [
    re.compile(r'"lowestPrice"\s*:\s*"?([\d,]+)'),
    re.compile(r'class="[^"]*lwst_prc[^"]*"[^>]*>[\s\S]{0,300}?<em[^>]*class="[^"]*prc_c[^"]*"[^>]*>([\d,]+)', re.I),
    re.compile(r'<em[^>]*class="[^"]*prc_c[^"]*"[^>]*>([\d,]+)', re.I),
    re.compile(r'최저가[\s\S]{0,200}?([\d]{1,3}(?:,\d{3})+)\s*원'),
]
MALL_PATTERNS = [
    re.compile(r'"lowestMallName"\s*:\s*"([^"]+)"'),
    re.compile(r'class="[^"]*mall_name[^"]*"[^>]*>\s*(?:<img[^>]*alt="([^"]+)"|([^<]{1,30}))', re.I),
]
TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', re.I)


def extract_danawa(html: str) -> Optional[Quote]:
    """순수 함수 — 테스트 대상."""
    q = extract_from_html(html)
    if q and q.price:
        q.currency = "KRW"
        return q
    price = None
    for pat in PRICE_PATTERNS:
        m = pat.search(html)
        if m:
            price = float(m.group(1).replace(",", ""))
            break
    if not price:
        return None
    mall = None
    for pat in MALL_PATTERNS:
        m = pat.search(html)
        if m:
            mall = next((g for g in m.groups() if g), None)
            if mall:
                mall = mall.strip()
                break
    t = TITLE_RE.search(html)
    return Quote(price=price, currency="KRW", title=t.group(1).strip() if t else None, seller=mall or "다나와 최저가", in_stock=True)


class DanawaAdapter(BaseAdapter):
    site = "danawa"
    priority = 20
    min_interval_hours = 12
    budget_per_run = 30

    def matches(self, product: Product) -> bool:
        return product.site == "danawa" and bool(PCODE_RE.search(product.url))

    def fetch(self, product: Product) -> Quote:
        if not allowed(product.url):
            raise AdapterError("robots.txt 가 자동 수집을 금지 — 북마클릿으로 직접 기록하세요")
        self.consume()
        with self.client() as c:
            r = c.get(product.url)
        if r.status_code in (403, 429):
            raise AdapterError(f"다나와 {r.status_code} 차단 — 북마클릿으로 직접 기록하세요")
        if r.status_code >= 400:
            raise AdapterError(f"HTTP {r.status_code}")
        q = extract_danawa(r.text)
        if not q:
            raise AdapterError("다나와 페이지에서 최저가를 찾지 못함 (구조 변경 가능) — 북마클릿 권장")
        q.external_id = PCODE_RE.search(product.url).group(1)  # type: ignore[union-attr]
        return q
