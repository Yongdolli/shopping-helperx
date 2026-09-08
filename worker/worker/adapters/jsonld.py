"""범용 어댑터: 상품 페이지의 JSON-LD(schema.org Product/Offer) · OpenGraph 메타에서 가격 추출.

대부분의 쇼핑몰(Best Buy, Walmart, Target, 11번가, 지마켓, 다나와, 알리 등)이 JSON-LD 를 넣어 두므로
전용 API 키가 없을 때의 기본 경로. 봇 차단이 강한 사이트(쿠팡·아마존·테무)는 실패할 수 있다.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional

from ..models import Product, Quote
from .base import AdapterError, BaseAdapter

JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
META_RE = re.compile(r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']', re.I)
META_RE2 = re.compile(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']([^"\']+)["\']', re.I)


def _walk(node: Any) -> Iterable[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def extract_from_html(html: str) -> Optional[Quote]:
    """HTML 문자열에서 Quote 추출. 순수 함수 — 테스트 대상."""
    # 1) JSON-LD Product
    for block in JSONLD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Product" not in types:
                continue
            offers = node.get("offers")
            offer = None
            for o in _walk(offers):
                ot = o.get("@type")
                if ot in ("Offer", "AggregateOffer") or "price" in o or "lowPrice" in o:
                    offer = o
                    break
            if not offer:
                continue
            price = BaseAdapter.parse_price(offer.get("price") or offer.get("lowPrice"))
            if price is None and isinstance(offer.get("priceSpecification"), dict):
                price = BaseAdapter.parse_price(offer["priceSpecification"].get("price"))
            if price is None:
                continue
            availability = str(offer.get("availability", "")).lower()
            in_stock = ("outofstock" not in availability) and ("soldout" not in availability)
            seller = offer.get("seller", {}).get("name") if isinstance(offer.get("seller"), dict) else None
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")
            # 정가: 일부 사이트가 highPrice / listPrice / 별도 priceSpecification 으로 표기
            list_price = BaseAdapter.parse_price(offer.get("listPrice") or node.get("listPrice"))
            if list_price is None and isinstance(offer.get("priceSpecification"), list):
                for ps in offer["priceSpecification"]:
                    if isinstance(ps, dict) and str(ps.get("priceType", "")).lower().endswith("listprice"):
                        list_price = BaseAdapter.parse_price(ps.get("price"))
            return Quote(
                price=price,
                currency=str(offer.get("priceCurrency") or "USD").upper(),
                title=node.get("name"),
                seller=seller,
                in_stock=in_stock,
                image_url=image,
                external_id=str(node.get("sku") or node.get("productID") or "") or None,
                model_no=node.get("model") or node.get("mpn"),
                list_price=list_price if list_price and list_price > price else None,
            )

    # 2) OpenGraph / product meta
    meta: dict[str, str] = {}
    for k, v in META_RE.findall(html):
        meta.setdefault(k.lower(), v)
    for v, k in META_RE2.findall(html):
        meta.setdefault(k.lower(), v)
    price = BaseAdapter.parse_price(
        meta.get("product:price:amount") or meta.get("og:price:amount") or meta.get("price")
    )
    if price is not None:
        orig = BaseAdapter.parse_price(meta.get("product:original_price:amount"))
        return Quote(
            price=price,
            currency=(meta.get("product:price:currency") or meta.get("og:price:currency") or "USD").upper(),
            title=meta.get("og:title"),
            image_url=meta.get("og:image"),
            in_stock="out of stock" not in (meta.get("product:availability", "").lower()),
            list_price=orig if orig and orig > price else None,
        )
    return None


class JsonLdAdapter(BaseAdapter):
    site = "generic"
    priority = 900  # 항상 마지막 후보

    def matches(self, product: Product) -> bool:
        return True

    def fetch(self, product: Product) -> Quote:
        from ..robots import allowed  # 지연 임포트 (테스트에서 네트워크 없이 extract_from_html 사용)

        if not allowed(product.url):
            raise AdapterError("robots.txt 가 자동 수집을 금지 — 북마클릿(설정 화면)으로 직접 기록하세요")
        with self.client() as c:
            r = c.get(product.url)
        if r.status_code >= 400:
            raise AdapterError(f"HTTP {r.status_code}")
        q = extract_from_html(r.text)
        if not q:
            raise AdapterError("페이지에서 가격을 찾지 못함 (JSON-LD/OG 없음 — 전용 어댑터 필요)")
        if q.currency == "USD" and product.currency != "USD" and product.site != "generic":
            q.currency = product.currency  # 사이트 기본 통화로 보정
        return q
