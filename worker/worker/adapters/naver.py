"""네이버 스마트스토어 / 브랜드스토어 상품 페이지 어댑터 (공식 API 없음 — 2026-07 쇼핑 검색 API 종료).

- 페이지에 박힌 `window.__PRELOADED_STATE__` JSON 에서 판매가·할인가·재고·판매자를 읽는다. 없으면 JSON-LD/OG 로 폴백.
- robots.txt 를 확인해 막혀 있으면 스스로 중단한다(AdapterError). 그 경우 북마클릿(사용자 브라우저 캡처)을 쓴다.
- 12시간 간격·실행당 20회. 네이버 가격비교(search.shopping.naver.com)는 차단이 강해 지원하지 않음.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional

from ..models import Product, Quote
from ..robots import allowed
from .base import AdapterError, BaseAdapter
from .jsonld import extract_from_html

STATE_RE = re.compile(r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)
HOSTS = ("smartstore.naver.com", "brand.naver.com")


def _walk(node: Any) -> Iterable[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def extract_from_state(html: str) -> Optional[Quote]:
    """__PRELOADED_STATE__ 에서 상품 노드(name + salePrice)를 찾아 Quote 로. 순수 함수 — 테스트 대상."""
    m = STATE_RE.search(html)
    if not m:
        return None
    try:
        state = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    for node in _walk(state):
        if "salePrice" not in node or "name" not in node:
            continue
        sale = BaseAdapter.parse_price(node.get("salePrice"))
        if sale is None:
            continue
        discounted = None
        bv = node.get("benefitsView") or {}
        for key in ("discountedSalePrice", "mobileDiscountedSalePrice"):
            discounted = BaseAdapter.parse_price(bv.get(key)) if isinstance(bv, dict) else None
            if discounted:
                break
        if discounted is None:
            discounted = BaseAdapter.parse_price(node.get("discountedSalePrice"))
        price = discounted if discounted else sale
        status = str(node.get("statusType") or node.get("productStatusType") or "SALE").upper()
        stock = node.get("stockQuantity")
        in_stock = status == "SALE" and (stock is None or int(stock) > 0)
        channel = node.get("channel") or {}
        image = (node.get("representImage") or {}).get("url") if isinstance(node.get("representImage"), dict) else None
        return Quote(
            price=price, currency="KRW", title=node.get("name"),
            seller=channel.get("channelName") if isinstance(channel, dict) else None,
            in_stock=in_stock, image_url=image,
            external_id=str(node.get("id") or node.get("productNo") or "") or None,
            list_price=sale if discounted and sale > discounted else None,
        )
    return None


class NaverStoreAdapter(BaseAdapter):
    site = "naver"
    priority = 20
    min_interval_hours = 12
    budget_per_run = 20

    def matches(self, product: Product) -> bool:
        return product.site == "naver" and any(h in product.url for h in HOSTS)

    def fetch(self, product: Product) -> Quote:
        if not allowed(product.url):
            raise AdapterError("robots.txt 가 자동 수집을 금지 — 북마클릿(설정 화면)으로 직접 기록하세요")
        self.consume()
        with self.client() as c:
            r = c.get(product.url)
        if r.status_code in (403, 429):
            raise AdapterError(f"네이버 {r.status_code} 차단 — 북마클릿으로 직접 기록하세요")
        if r.status_code >= 400:
            raise AdapterError(f"HTTP {r.status_code}")
        q = extract_from_state(r.text) or extract_from_html(r.text)
        if not q:
            raise AdapterError("페이지에서 가격을 찾지 못함 (로그인/봇 차단 페이지일 수 있음)")
        q.currency = "KRW"
        return q
