"""데모/테스트용 어댑터. URL 이 mock:// 로 시작하면 랜덤 워크 가격을 돌려준다.
기준 가격은 `mock://site/slug?base=449000` 처럼 URL 에 넣는다.
"""
from __future__ import annotations

import hashlib
import random
from urllib.parse import parse_qs, urlparse


from ..models import Product, Quote
from .base import BaseAdapter


def mock_base(url: str, currency: str) -> float:
    q = parse_qs(urlparse(url).query)
    if "base" in q:
        return float(q["base"][0])
    seed = int(hashlib.md5(url.encode()).hexdigest()[:8], 16)
    return float(10_000 + seed % 990_000 if currency == "KRW" else 20 + seed % 980)


class MockAdapter(BaseAdapter):
    site = "mock"
    priority = 0

    def matches(self, product: Product) -> bool:
        return product.url.startswith("mock://")

    def fetch(self, product: Product) -> Quote:
        base = mock_base(product.url, product.currency)
        rnd = random.Random()
        drift = rnd.uniform(-0.04, 0.04)
        if rnd.random() < 0.08:  # 가끔 급락
            drift -= rnd.uniform(0.10, 0.25)
        q = parse_qs(urlparse(product.url).query)
        list_price = float(q["list"][0]) if "list" in q else None
        seller = q["seller"][0] if "seller" in q else "mock-seller"
        return Quote(price=round(base * (1 + drift), 2 if product.currency != "KRW" else 0),
                     currency=product.currency, title=product.title, seller=seller,
                     in_stock=rnd.random() > 0.03, list_price=list_price)
