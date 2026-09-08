"""AliExpress Affiliate(Portals) Open API — aliexpress.affiliate.productdetail.get
https://openservice.aliexpress.com/doc/doc.htm  (앱키/시크릿 필요, MD5 서명)
"""
from __future__ import annotations

import hashlib
import re
import time

from ..config import settings
from ..models import Product, Quote
from .base import AdapterError, BaseAdapter

ITEM_RE = re.compile(r"/item/(\d+)\.html")
GATEWAY = "https://api-sg.aliexpress.com/sync"


def sign(params: dict[str, str], secret: str) -> str:
    base = secret + "".join(k + params[k] for k in sorted(params)) + secret
    return hashlib.md5(base.encode("utf-8")).hexdigest().upper()


class AliExpressAdapter(BaseAdapter):
    site = "aliexpress"
    priority = 10

    def available(self) -> bool:
        return bool(settings.aliexpress_app_key and settings.aliexpress_app_secret)

    def matches(self, product: Product) -> bool:
        return product.site == "aliexpress" and bool(ITEM_RE.search(product.url))

    def fetch(self, product: Product) -> Quote:
        item_id = ITEM_RE.search(product.url).group(1)  # type: ignore[union-attr]
        params = {
            "app_key": settings.aliexpress_app_key,
            "method": "aliexpress.affiliate.productdetail.get",
            "timestamp": str(int(time.time() * 1000)),
            "sign_method": "md5",
            "format": "json",
            "v": "2.0",
            "product_ids": item_id,
            "target_currency": "USD",
            "target_language": "KO",
            "ship_to_country": "KR",
        }
        params["sign"] = sign(params, settings.aliexpress_app_secret)
        with self.client() as c:
            r = c.get(GATEWAY, params=params)
        if r.status_code != 200:
            raise AdapterError(f"AliExpress {r.status_code}")
        d = r.json()
        try:
            item = d["aliexpress_affiliate_productdetail_get_response"]["resp_result"]["result"]["products"]["product"][0]
        except (KeyError, IndexError, TypeError):
            raise AdapterError(f"AliExpress 응답 형식 오류: {str(d)[:160]}")
        price = self.parse_price(item.get("target_sale_price") or item.get("sale_price"))
        if price is None:
            raise AdapterError("AliExpress: 가격 없음")
        return Quote(
            price=price, currency=item.get("target_sale_price_currency", "USD"),
            title=item.get("product_title"), seller=item.get("shop_name"),
            image_url=item.get("product_main_image_url"), external_id=item_id,
        )
