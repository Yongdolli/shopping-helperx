from __future__ import annotations

from ..models import Product
from .aliexpress import AliExpressAdapter
from .base import AdapterError, BaseAdapter
from .bestbuy import BestBuyAdapter
from .coupang import CoupangAdapter
from .danawa import DanawaAdapter
from .ebay import EbayAdapter
from .elevenst import ElevenStAdapter
from .jsonld import JsonLdAdapter
from .mock import MockAdapter
from .naver import NaverStoreAdapter

# 새 사이트 추가: 여기 한 줄만.
ADAPTERS: list[BaseAdapter] = sorted(
    [MockAdapter(), CoupangAdapter(), EbayAdapter(), BestBuyAdapter(), ElevenStAdapter(), AliExpressAdapter(),
     NaverStoreAdapter(), DanawaAdapter(), JsonLdAdapter()],
    key=lambda a: a.priority,
)


def get_adapter(product: Product) -> BaseAdapter:
    for a in ADAPTERS:
        if a.available() and a.matches(product):
            return a
    raise AdapterError(f"어댑터 없음: {product.url}")
