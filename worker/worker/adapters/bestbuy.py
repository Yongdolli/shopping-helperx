"""Best Buy Products API (무료 키). https://bestbuyapis.github.io/api-documentation/"""
from __future__ import annotations

import re

from ..config import settings
from ..models import Product, Quote
from .base import AdapterError, BaseAdapter

SKU_RE = re.compile(r"skuId=(\d+)|/(\d{7,8})\.p\b")


class BestBuyAdapter(BaseAdapter):
    site = "bestbuy"
    priority = 10

    def available(self) -> bool:
        return bool(settings.bestbuy_api_key)

    def matches(self, product: Product) -> bool:
        return product.site == "bestbuy" and bool(SKU_RE.search(product.url))

    def fetch(self, product: Product) -> Quote:
        m = SKU_RE.search(product.url)
        sku = m.group(1) or m.group(2)  # type: ignore[union-attr]
        with self.client() as c:
            r = c.get(
                f"https://api.bestbuy.com/v1/products/{sku}.json",
                params={"apiKey": settings.bestbuy_api_key,
                        "show": "sku,name,salePrice,regularPrice,onlineAvailability,image,modelNumber,manufacturer"},
            )
        if r.status_code != 200:
            raise AdapterError(f"BestBuy {r.status_code}: {r.text[:120]}")
        d = r.json()
        return Quote(
            price=float(d["salePrice"]),
            currency="USD",
            title=d.get("name"),
            seller="Best Buy",
            in_stock=bool(d.get("onlineAvailability", True)),
            image_url=d.get("image"),
            external_id=str(d.get("sku")),
            model_no=d.get("modelNumber"),
        )
