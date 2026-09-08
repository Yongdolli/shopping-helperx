"""11번가 OpenAPI ProductInfo. https://openapi.11st.co.kr (XML 응답)"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..config import settings
from ..models import Product, Quote
from .base import AdapterError, BaseAdapter

PRD_RE = re.compile(r"/products/(?:pa/)?(\d+)|prdNo=(\d+)")


class ElevenStAdapter(BaseAdapter):
    site = "11st"
    priority = 10

    def available(self) -> bool:
        return bool(settings.elevenst_api_key)

    def matches(self, product: Product) -> bool:
        return product.site == "11st" and bool(PRD_RE.search(product.url))

    def fetch(self, product: Product) -> Quote:
        m = PRD_RE.search(product.url)
        prd_no = m.group(1) or m.group(2)  # type: ignore[union-attr]
        with self.client() as c:
            r = c.get(
                "https://openapi.11st.co.kr/openapi/OpenApiService.tmall",
                params={"key": settings.elevenst_api_key, "apiCode": "ProductInfo", "productCode": prd_no},
            )
        if r.status_code != 200:
            raise AdapterError(f"11st {r.status_code}")
        root = ET.fromstring(r.content)
        node = root.find(".//Product") or root

        def txt(tag: str) -> str | None:
            el = node.find(tag)
            return el.text.strip() if el is not None and el.text else None

        price = self.parse_price(txt("SalePrice") or txt("ProductPrice"))
        if price is None:
            raise AdapterError("11st: 가격 필드 없음")
        return Quote(
            price=price, currency="KRW", title=txt("ProductName"), seller=txt("SellerNick") or "11번가",
            in_stock=(txt("SoldOut") or "N").upper() != "Y", image_url=txt("ProductImage300") or txt("ProductImage"),
            external_id=prd_no,
        )
