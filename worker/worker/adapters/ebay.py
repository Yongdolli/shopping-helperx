"""eBay Browse API (무료 개발자 키). https://developer.ebay.com/api-docs/buy/browse/overview.html"""
from __future__ import annotations

import base64
import re
import time

from ..config import settings
from ..models import Product, Quote
from .base import AdapterError, BaseAdapter

ITEM_RE = re.compile(r"/itm/(?:[^/]+/)?(\d{9,15})")
_token_cache: dict[str, tuple[str, float]] = {}


class EbayAdapter(BaseAdapter):
    site = "ebay"
    priority = 10

    def available(self) -> bool:
        return bool(settings.ebay_client_id and settings.ebay_client_secret)

    def matches(self, product: Product) -> bool:
        return product.site == "ebay" and bool(ITEM_RE.search(product.url))

    def _token(self) -> str:
        tok = _token_cache.get("t")
        if tok and tok[1] > time.time() + 60:
            return tok[0]
        creds = base64.b64encode(f"{settings.ebay_client_id}:{settings.ebay_client_secret}".encode()).decode()
        with self.client() as c:
            r = c.post(
                "https://api.ebay.com/identity/v1/oauth2/token",
                headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
            )
        if r.status_code != 200:
            raise AdapterError(f"eBay 토큰 실패 {r.status_code}")
        data = r.json()
        _token_cache["t"] = (data["access_token"], time.time() + int(data.get("expires_in", 7200)))
        return data["access_token"]

    def fetch(self, product: Product) -> Quote:
        item_id = ITEM_RE.search(product.url).group(1)  # type: ignore[union-attr]
        with self.client() as c:
            r = c.get(
                f"https://api.ebay.com/buy/browse/v1/item/v1|{item_id}|0",
                headers={"Authorization": f"Bearer {self._token()}",
                         "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            )
        if r.status_code != 200:
            raise AdapterError(f"eBay item {r.status_code}: {r.text[:120]}")
        d = r.json()
        price = d.get("price", {})
        return Quote(
            price=float(price.get("value")),
            currency=price.get("currency", "USD"),
            title=d.get("title"),
            seller=(d.get("seller") or {}).get("username"),
            in_stock=(d.get("estimatedAvailabilities") or [{}])[0].get("estimatedAvailabilityStatus", "IN_STOCK") == "IN_STOCK",
            image_url=(d.get("image") or {}).get("imageUrl"),
            external_id=item_id,
            model_no=d.get("mpn"),
        )
