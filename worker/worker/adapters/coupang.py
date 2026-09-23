"""쿠팡 파트너스 Open API (무료, 제휴 가입 필요). https://developers.coupang.com/ko

제약:
- 상품 ID 로 직접 조회하는 엔드포인트가 없다 → 상품명으로 검색해서 URL 의 productId 와 매칭.
- 공식 문서는 분당 50회지만 실제로는 시간당 10회 안팎에서 403 이 난다는 보고가 많음.
  → 실행당 예산 8회, 상품당 최소 6시간 간격. 등록 시 상품명이 반드시 필요.
- 검색 결과엔 정가(list_price)가 없어 가짜 할인 탐지는 쿠팡에선 동작하지 않음.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from ..config import settings
from ..models import Product, Quote
from .base import AdapterError, BaseAdapter

DOMAIN = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"
PRODUCT_RE = re.compile(r"/vp/products/(\d+)")


def sign(method: str, path: str, query: str, access_key: str, secret_key: str, now: datetime | None = None) -> str:
    """쿠팡 파트너스 HMAC 서명 헤더. 순수 함수 — 테스트 대상."""
    now = now or datetime.now(timezone.utc)
    signed_date = now.strftime("%y%m%dT%H%M%SZ")
    message = signed_date + method + path + query
    signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={signed_date}, signature={signature}"


def pick_match(items: list[dict], product_id: str) -> dict | None:
    for it in items:
        if str(it.get("productId")) == product_id:
            return it
    return None


class CoupangAdapter(BaseAdapter):
    site = "coupang"
    priority = 10
    min_interval_hours = 6
    budget_per_run = 5   # 딜 시세(market.py) 3회와 합쳐 시간당 8회 이하 — 계정당 ~10회/시간 넘으면 403·정지 위험

    def available(self) -> bool:
        return bool(settings.coupang_access_key and settings.coupang_secret_key)

    def matches(self, product: Product) -> bool:
        return product.site == "coupang" and bool(PRODUCT_RE.search(product.url))

    def fetch(self, product: Product) -> Quote:
        if not product.title or product.title == product.url:
            raise AdapterError("쿠팡은 검색 매칭 방식이라 상품명이 필요합니다 (등록 시 상품명 입력)")
        self.consume()
        product_id = PRODUCT_RE.search(product.url).group(1)  # type: ignore[union-attr]
        keyword = re.sub(r"\s+", " ", product.title)[:60]
        query = urlencode({"keyword": keyword, "limit": 20})
        auth = sign("GET", SEARCH_PATH, query, settings.coupang_access_key, settings.coupang_secret_key)
        with self.client() as c:
            r = c.get(f"{DOMAIN}{SEARCH_PATH}?{query}", headers={"Authorization": auth})
        if r.status_code == 403:
            raise AdapterError("쿠팡 403 — 호출 제한 또는 키 오류 (3회 누적 시 계정 정지 주의)")
        if r.status_code != 200:
            raise AdapterError(f"쿠팡 {r.status_code}: {r.text[:120]}")
        d = r.json()
        if str(d.get("rCode")) != "0":
            raise AdapterError(f"쿠팡 API 오류: {d.get('rMessage')}")
        items = (d.get("data") or {}).get("productData") or []
        it = pick_match(items, product_id)
        if not it:
            raise AdapterError(f"검색 결과 {len(items)}건에 productId {product_id} 없음 — 상품명을 더 정확히")
        return Quote(
            price=float(it["productPrice"]), currency="KRW", title=it.get("productName"),
            seller="쿠팡" + (" 로켓" if it.get("isRocket") else ""), in_stock=True,
            image_url=it.get("productImage"), external_id=product_id,
        )
