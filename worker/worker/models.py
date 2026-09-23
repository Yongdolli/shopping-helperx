from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

# 호스트명 → (site, country, currency)
SITE_TABLE: dict[str, tuple[str, str, str]] = {
    "coupang.com": ("coupang", "KR", "KRW"),
    "11st.co.kr": ("11st", "KR", "KRW"),
    "gmarket.co.kr": ("gmarket", "KR", "KRW"),
    "auction.co.kr": ("auction", "KR", "KRW"),
    "ssg.com": ("ssg", "KR", "KRW"),
    "lotteon.com": ("lotteon", "KR", "KRW"),
    "danawa.com": ("danawa", "KR", "KRW"),
    "enuri.com": ("enuri", "KR", "KRW"),
    "musinsa.com": ("musinsa", "KR", "KRW"),
    "oliveyoung.co.kr": ("oliveyoung", "KR", "KRW"),
    "kurly.com": ("kurly", "KR", "KRW"),
    "smartstore.naver.com": ("naver", "KR", "KRW"),
    "brand.naver.com": ("naver", "KR", "KRW"),
    "aliexpress.com": ("aliexpress", "CN", "USD"),
    "aliexpress.us": ("aliexpress", "CN", "USD"),
    "temu.com": ("temu", "CN", "USD"),
    "shein.com": ("shein", "CN", "USD"),
    "taobao.com": ("taobao", "CN", "CNY"),
    "tmall.com": ("tmall", "CN", "CNY"),
    "jd.com": ("jd", "CN", "CNY"),
    "1688.com": ("1688", "CN", "CNY"),
    "amazon.com": ("amazon", "US", "USD"),
    "ebay.com": ("ebay", "US", "USD"),
    "walmart.com": ("walmart", "US", "USD"),
    "bestbuy.com": ("bestbuy", "US", "USD"),
    "target.com": ("target", "US", "USD"),
    "etsy.com": ("etsy", "US", "USD"),
}

# 사이트별로 "옵션(variant)" 을 구분하는 URL 파라미터.
# 같은 상품 페이지라도 이 값이 다르면 다른 가격 시계열로 취급한다.
VARIANT_PARAMS: dict[str, tuple[str, ...]] = {
    "coupang": ("vendorItemId", "itemId"),
    "aliexpress": ("sku_id",),
    "amazon": ("th", "psc"),      # ASIN 자체가 옵션이므로 보통 URL 경로로 구분됨
    "ebay": ("var",),
    "11st": ("optionNo",),
    "gmarket": ("optionNo",),
    "walmart": ("selected",),
    "bestbuy": ("skuId",),
}


MANUAL_ONLY_MARK = "robots.txt"


def is_manual_only(error: Optional[str]) -> bool:
    """영구적 '자동 수집 불가'(robots.txt 금지) — 실패로 세지 않고, 북마클릿/확장 전용으로 다룬다."""
    return bool(error) and MANUAL_ONLY_MARK in error


def detect_site(url: str) -> tuple[str, str, str]:
    host = (urlparse(url).hostname or "").lower()
    for domain, info in SITE_TABLE.items():
        if host == domain or host.endswith("." + domain):
            return info
    return ("generic", "US", "USD")


def parse_variant(url: str, site: Optional[str] = None) -> Optional[str]:
    """URL 쿼리에서 옵션 식별자를 뽑는다. 예) coupang ...?vendorItemId=123 → 'vendorItemId=123'"""
    site = site or detect_site(url)[0]
    q = parse_qs(urlparse(url).query)
    parts = [f"{k}={q[k][0]}" for k in VARIANT_PARAMS.get(site, ()) if k in q and q[k]]
    return "&".join(parts) or None


@dataclass
class Product:
    id: str
    title: str
    url: str
    site: str
    country: str = "KR"
    currency: str = "KRW"
    external_id: Optional[str] = None
    model_no: Optional[str] = None
    image_url: Optional[str] = None
    user_id: Optional[str] = None
    active: bool = True
    variant: Optional[str] = None
    fail_count: int = 0
    last_error: Optional[str] = None
    last_fetched_at: Optional[datetime] = None
    verified: bool = False            # 사용자가 '정품 확인됨' 표시
    risk_level: Optional[str] = None  # low | medium | high (마지막 수집 시 계산)
    risk_reasons: Optional[str] = None
    category: Optional[str] = None    # 관세 계산용 (전자/의류/신발/화장품/식품/장난감/가방/기타)
    target_price: Optional[float] = None   # 사용자 목표가 (이하가 되면 kind=target 알림)
    tags: Optional[str] = None             # 쉼표 구분 태그
    purchased_at: Optional[datetime] = None
    purchased_price: Optional[float] = None


@dataclass
class PriceSnapshot:
    product_id: str
    price: float
    currency: str
    seller: Optional[str] = None
    in_stock: bool = True
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    list_price: Optional[float] = None  # 사이트가 표시하는 '정가/원래 가격'
    suspect: bool = False               # 극단값 — 다음 수집에서 확인되기 전까지 기준선·알림에서 제외


@dataclass
class Quote:
    """어댑터가 돌려주는 1회 조회 결과."""

    price: float
    currency: str
    title: Optional[str] = None
    seller: Optional[str] = None
    in_stock: bool = True
    image_url: Optional[str] = None
    external_id: Optional[str] = None
    model_no: Optional[str] = None
    list_price: Optional[float] = None


@dataclass
class Alert:
    product_id: str
    kind: str  # target | drop | low | restock | fake | paused
    price: float
    baseline: Optional[float]
    pct: Optional[float]
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    note: Optional[str] = None  # 예: '판매자 변경: A → B'
    id: Optional[str] = None
    notified: bool = True        # False = 다이제스트 대기 (digest.py 가 모아서 발송)


@dataclass
class UserSettings:
    user_id: Optional[str] = None
    threshold_pct: float = 10.0
    window_days: int = 90
    notify_email: bool = False
    notify_telegram: bool = False
    notify_push: bool = True
    email: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    digest: bool = True          # 하루 3회 모아 받기 (False = 감지 즉시 발송)
    instant_target: bool = True  # digest 여도 목표가 도달(target)은 즉시
    deal_min_pct: float = 10.0   # 딜: 평소보다(없으면 표시 할인율) 이만큼 이상 싸면 다이제스트에 포함
    deal_keywords: Optional[str] = None   # 관심 키워드 (쉼표 구분) — 일치하면 할인율 없어도 다이제스트에 포함


@dataclass
class Deal:
    """핫딜 커뮤니티에서 모은 딜 1건 (deals.py). url = 게시글 주소, 중복 제거 키."""

    url: str
    source: str                   # ppomppu | ruliweb | clien | quasarzone | fmkorea
    site: str                     # 우리 site 키 또는 상점명 소문자
    site_label: str               # 원문 [사이트]
    title: str
    price: Optional[float]
    currency: str = "KRW"
    shipping: Optional[str] = None
    pct: Optional[float] = None   # 제목에 명시된 할인율만
    posted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    image_url: Optional[str] = None
    category: Optional[str] = None
    shop_url: Optional[str] = None      # 게시글에서 찾은 상점 상품 주소 (enrich) → 원클릭 추적
    list_price: Optional[float] = None  # 상점 페이지 정가 (enrich) → pct 근거
    enriched: bool = False              # 보강 시도 완료 (실패해도 True — 재시도 안 함)
    ref_price: Optional[float] = None   # 평소 가격 (market.py: 다나와 전체 쇼핑몰 최저가 관측 중앙값)
    ref_name: Optional[str] = None
    ref_url: Optional[str] = None
    below_pct: Optional[float] = None   # 평소 대비 % (양수 = 평소보다 쌈)
    ref_checked: bool = False           # 시세 확인 시도 완료

    @property
    def effective_pct(self) -> Optional[float]:
        """판단에 쓰는 할인율: 시세 대비(below_pct)가 있으면 그것, 없으면 게시글·상점 표시 할인율."""
        return self.below_pct if self.below_pct is not None else self.pct


@dataclass
class PushSubscription:
    endpoint: str
    p256dh: str
    auth: str
    user_id: Optional[str] = None
