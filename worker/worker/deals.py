"""딜 피드 — 등록하지 않은 상품까지 '모든 사이트'의 할인을 모아 본다.

소스: 핫딜 커뮤니티(뽐뿌 RSS · 루리웹 RSS · 클리앙 알뜰구매 · 퀘이사존 지름/할인정보 · 에펨코리아 핫딜).
사람들이 이미 모든 쇼핑몰의 할인을 올려 두므로, 이를 읽어 `[사이트] 상품명 (가격/배송)` 을 파싱한다.
- 할인율(pct)은 제목에 'N%'·'반값' 이 있을 때만 확정. 없으면 None (커뮤니티 글은 대개 가격만 있다).
- robots.txt 준수, 소스별 실패 격리(한 곳이 막혀도 나머지는 수집), 게시글 URL 로 중복 제거, 7일 지나면 삭제.
- `python -m worker deals` — collect 크론에서 매시 실행. 다이제스트(digest.py)가 관심 키워드·최소 할인율에 맞는 딜을 함께 보낸다.
- **보강(enrich)**: 커뮤니티 글엔 할인율이 거의 없으므로, 새 딜은 게시글을 열어 상점 상품 주소(shop_url)를 찾고, 상점 페이지의 JSON-LD 에서
  정가(있으면) 또는 상점 표시가를 읽어, 딜 가격이 그보다 싸면 pct 를 계산한다. 실행당 ENRICH_PER_RUN 건, robots 준수, 봇 차단 사이트(BLOCKED_HOSTS)는 상점 페이지 생략.
  shop_url 이 있으면 웹 딜 탭에서 원클릭 추적.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

import time
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .adapters.jsonld import extract_from_html
from .config import settings
from .models import SITE_TABLE, Deal
from .robots import allowed

log = logging.getLogger(__name__)

KEEP_DAYS = 7
MIN_REF_RATIO = 0.5          # 딜가 / 상점 정가 — 상점 페이지 '정가'는 다른 옵션·세트 값이 섞여 50%↓ 초과 할인은 믿지 않음
TIMEOUT = 15
ENRICH_PER_RUN = 25          # 실행당 게시글·상점 페이지 보강 상한 (매시 크론 → 하루 600건)
ENRICH_DELAY = 0.7
SHOP_HOSTS = tuple(SITE_TABLE) + ("shopping.naver.com", "ohou.se", "wemakeprice.com", "tmon.co.kr", "gift.kakao.com", "store.steampowered.com",
                                  "apple.com", "samsung.com", "lge.co.kr", "costco.co.kr", "homeplus.co.kr", "emart.ssg.com", "kream.co.kr", "29cm.co.kr", "hmall.com", "gsshop.com", "cjonstyle.com", "lotte.com")
# 봇 차단(403)이 확인된 상점 — 상점 페이지는 읽지 않고 링크만 저장 (실측 2026-09: 지마켓·옥션·오늘의집 403)
BLOCKED_HOSTS = ("coupang.com", "naver.com", "amazon.com", "temu.com", "shein.com", "gmarket.co.kr", "auction.co.kr", "ohou.se")
SHORTENERS = ("naver.me", "m.site.naver.com", "coupa.ng", "link.coupang.com", "bit.ly", "me2.do", "han.gl", "url.kr", "vo.la", "lrl.kr", "tinyurl.com", "s.click.aliexpress.com", "a.aliexpress.com")
SKIP_TITLES = ("블라인드 처리된", "삭제된 게시물", "관리자 삭제")
SKIP_SITES = {"ios", "android", "wearos", "watchos", "macos"}    # 앱 리딤·무료앱 글은 상품이 아님
REDIRECT_PARAMS = ("url", "link", "target", "u", "ol", "ourl", "redirect", "goto")

# 커뮤니티가 쓰는 상점 이름 → 우리 site 키 (부분 일치, 소문자)
SITE_ALIASES: list[tuple[str, str]] = [
    ("쿠팡", "coupang"), ("로켓", "coupang"), ("지마켓", "gmarket"), ("g마켓", "gmarket"), ("옥션", "auction"),
    ("11번가", "11st"), ("십일번가", "11st"), ("스마트스토어", "naver"), ("네이버", "naver"), ("네버", "naver"),
    ("알리", "aliexpress"), ("테무", "temu"), ("아마존", "amazon"), ("amazon", "amazon"), ("이베이", "ebay"), ("ebay", "ebay"),
    ("롯데온", "lotteon"), ("ssg", "ssg"), ("쓱", "ssg"), ("다나와", "danawa"), ("무신사", "musinsa"), ("올리브영", "oliveyoung"),
    ("컬리", "kurly"), ("위메프", "wemakeprice"), ("티몬", "tmon"), ("카카오", "kakao"), ("토스", "toss"), ("오늘의집", "ohouse"),
    ("스팀", "steam"), ("애플", "apple"), ("삼성", "samsung"), ("lg", "lg"), ("코스트코", "costco"), ("홈플러스", "homeplus"), ("이마트", "emart"),
]

SITE_RE = re.compile(r"^\s*[\[【(]\s*([^\]】)]{1,24}?)\s*[\]】)]\s*")
PRICE_TAIL_RE = re.compile(r"[(（]\s*([\d,]{2,})\s*원?\s*(?:/\s*([^)）]{0,24}?))?\s*[)）]\s*$")   # (29,500원/무료)
PRICE_SLASH_RE = re.compile(r"\s*/\s*([\d,]{2,})\s*원\s*(?:/\s*(\S{1,12}))?\s*$")            # 루리웹 "… / 23,300원"
PRICE_ANY_RE = re.compile(r"([\d,]{4,})\s*원")
PCT_RE = re.compile(r"(\d{1,2})\s*%")
END_RE = re.compile(r"(종료|품절|마감|매진|솔드아웃|sold\s*out)", re.I)   # 제목에 이게 있으면 끝난 딜
FREE_WORDS = ("무료", "무배", "free", "네멤무배", "멤버십무배")


@dataclass
class ParsedTitle:
    site_label: str
    name: str
    price: Optional[float]
    shipping: Optional[str]
    pct: Optional[float]


def _num(s: str) -> Optional[float]:
    try:
        v = float(s.replace(",", ""))
        return v if v > 0 else None
    except ValueError:
        return None


def parse_title(raw: str, price_hint: Optional[float] = None, shipping_hint: Optional[str] = None) -> ParsedTitle:
    """'[롯데온] QCY 이어폰 1+1 (29,500원/무료)' → site=롯데온, name='QCY 이어폰 1+1', price=29500, shipping='무료'."""
    t = html.unescape(raw).replace("\xa0", " ").strip()
    site = ""
    m = SITE_RE.match(t)
    if m:
        site, t = m.group(1).strip(), t[m.end():].strip()
    price, shipping = price_hint, shipping_hint
    m = PRICE_TAIL_RE.search(t)
    if m:
        price = _num(m.group(1)) or price
        shipping = (m.group(2) or "").strip() or shipping
        t = t[:m.start()].strip()
    else:
        m = PRICE_SLASH_RE.search(t)
        if m:
            price = _num(m.group(1)) or price
            shipping = (m.group(2) or "").strip() or shipping
            t = t[:m.start()].strip()
        elif price is None:
            m = PRICE_ANY_RE.search(t)
            if m:
                price = _num(m.group(1))
    pct: Optional[float] = None
    m = PCT_RE.search(t)
    if m and 5 <= int(m.group(1)) <= 95:
        pct = float(m.group(1))
    elif "반값" in t:
        pct = 50.0
    if shipping and any(w in shipping.lower() for w in FREE_WORDS):
        shipping = "무료"
    return ParsedTitle(site, re.sub(r"\s+", " ", t).strip(" -·/"), price, shipping, pct)


def site_key(label: str) -> str:
    low = label.lower().strip()
    for alias, key in SITE_ALIASES:
        if alias in low:
            return key
    return low or "unknown"


def _get(url: str) -> str:
    if not allowed(url):
        raise RuntimeError(f"robots.txt 금지: {url}")
    r = httpx.get(url, headers={"User-Agent": settings.user_agent, "Accept-Language": "ko-KR,ko;q=0.9"}, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _rss_items(xml: str) -> list[dict[str, str]]:
    out = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        d = {}
        for tag in ("title", "link", "pubDate", "category", "description"):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
            if m:
                v = m.group(1).strip()
                v = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v, flags=re.S)
                d[tag] = html.unescape(v)
        if d.get("title") and d.get("link"):
            out.append(d)
    return out


def _when(s: Optional[str], now: datetime) -> datetime:
    if not s:
        return now
    try:
        dt = parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return now


def _make(source: str, url: str, title: str, now: datetime, posted: datetime, price_hint: Optional[float] = None,
          shipping_hint: Optional[str] = None, image_url: Optional[str] = None, category: Optional[str] = None) -> Optional[Deal]:
    p = parse_title(title, price_hint, shipping_hint)
    if not p.name or len(p.name) < 2 or any(w in p.name for w in SKIP_TITLES):
        return None
    site = site_key(p.site_label)
    if site in SKIP_SITES:
        return None
    if url.startswith("http://www.ppomppu.co.kr"):        # http 는 JS 리다이렉트 페이지 → https 로
        url = "https://" + url[len("http://"):]
    d = Deal(url, source, site, p.site_label or "", p.name, p.price, "KRW", p.shipping, p.pct,
             posted, now, image_url, category)
    d.ended = bool(END_RE.search(title))
    return d


# ---------------------------------------------------------------- 소스
def fetch_ppomppu(now: datetime) -> list[Deal]:
    xml = _get("https://www.ppomppu.co.kr/rss.php?id=ppomppu")
    out = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        it = (_rss_items(f"<item>{block}</item>") or [None])[0]
        if not it:
            continue
        d = _make("ppomppu", it["link"], it["title"], now, _when(it.get("pubDate"), now))
        if not d:
            continue
        hits = re.search(r"<hits>\s*\[(\d+)\|(\d+)\|(\d+)\|", block)       # [댓글|조회|추천|…]
        if hits:
            d.comments, d.recommends = int(hits.group(1)), int(hits.group(3))
        out.append(d)
    return out


def ruliweb_stats(page: str) -> dict[str, tuple[int, int, bool]]:
    """루리웹 목록 페이지: 글 URL → (추천, 댓글, 종료). RSS 에는 이 정보가 없다."""
    out = {}
    for row in re.findall(r'<tr class="table_body[^"]*"(.*?)</tr>', page, re.S):
        a = re.search(r'href="(https://bbs\.ruliweb\.com/market/board/1020/read/\d+)', row)
        if not a:
            continue
        rec = re.search(r'<td class="recomd">\s*(\d+)', row)
        rep = re.search(r'class="num_reply"[^>]*>\s*\((\d+)\)', row)
        out[a.group(1)] = (int(rec.group(1)) if rec else 0, int(rep.group(1)) if rep else 0, "[종료]" in row)
    return out


def fetch_ruliweb(now: datetime) -> list[Deal]:
    items = _rss_items(_get("https://bbs.ruliweb.com/market/board/1020/rss"))
    try:
        stats = ruliweb_stats(_get("https://bbs.ruliweb.com/market/board/1020"))
    except Exception as e:  # noqa: BLE001 — 통계는 없어도 딜 수집은 계속
        log.debug("루리웹 목록 통계 실패: %s", str(e)[:80])
        stats = {}
    out = []
    for it in items:
        img = re.search(r'src="([^"]+)"', it.get("description", "") or "")
        d = _make("ruliweb", it["link"], it["title"], now, _when(it.get("pubDate"), now), image_url=img.group(1) if img else None,
                  category=it.get("category"))
        if d:
            s = stats.get(d.url.split("?")[0])
            if s:
                d.recommends, d.comments = s[0], s[1]
                d.ended = d.ended or s[2]
            out.append(d)
    # RSS 에서 빠진 예전 글의 종료·추천 갱신용 (제목 없이 url·통계만 — run_deals 가 기존 딜에만 반영)
    rss_urls = {d.url for d in out}
    for url, (rec, com, ended) in stats.items():
        if url not in rss_urls:
            out.append(Deal(url, "ruliweb", "", "", "", None, recommends=rec, comments=com, ended=ended, posted_at=now, fetched_at=now))
    return out


def fetch_clien(now: datetime) -> list[Deal]:
    page = _get("https://www.clien.net/service/board/jirum")
    out = []
    for m in re.finditer(r'<div class="list_item symph_row jirum[^"]*"(.*?)<div class="list_time">(.*?)</div>', page, re.S):
        body, timeblock = m.group(1), m.group(2)
        a = re.search(r'<a href="(/service/board/jirum/(\d+))[^"]*"[^>]*data-role="list-title-text"[^>]*>(.*?)</a>', body, re.S)
        if not a:
            continue
        title = re.sub(r"<[^>]+>", "", a.group(3))
        ts = re.search(r'<span class="timestamp">([\d\- :]+)</span>', timeblock)
        posted = now
        if ts:
            try:
                posted = datetime.strptime(ts.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=9)))
            except ValueError:
                pass
        d = _make("clien", "https://www.clien.net" + a.group(1), title, now, posted)
        if d:
            votes = re.search(r'class="list_votes"><i[^>]*></i>\s*(\d+)', body)
            cmt = re.search(r'data-comment-count=(\d+)', m.group(0))
            d.recommends = int(votes.group(1)) if votes else 0
            d.comments = int(cmt.group(1)) if cmt else None
            d.ended = d.ended or '<span class="icon_info">품절</span>' in body
            out.append(d)
    return out


def fetch_quasarzone(now: datetime) -> list[Deal]:
    page = _get("https://quasarzone.com/bbs/qb_saleinfo")
    out = []
    links = list(re.finditer(r'<a href="(/bbs/qb_(?:partner)?saleinfo/views/\d+)"\s+class="subject-link\s*"[^>]*>(.*?)</a>', page, re.S))
    for i, m in enumerate(links):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        rest = page[m.end(): links[i + 1].start() if i + 1 < len(links) else m.end() + 4000]
        pm = re.search(r'v2-list-row__price">\s*[￦₩]?\s*([\d,]+)', rest)
        d = _make("quasarzone", "https://quasarzone.com" + href, title, now, now, price_hint=_num(pm.group(1)) if pm else None)
        if d:
            out.append(d)
    return out


def fetch_fmkorea(now: datetime) -> list[Deal]:
    page = _get("https://www.fmkorea.com/hotdeal")
    out = []
    for m in re.finditer(r'<a href="(/\d+)" class="\s*hotdeal_var8"[^>]*>\s*<span class="ellipsis-target">(.*?)</span>.*?<div class="hotdeal_info">(.*?)</div>', page, re.S):
        href, title, info = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)), re.sub(r"<[^>]+>", "", m.group(3))
        shop = re.search(r"쇼핑몰:\s*(\S+)", info)
        price = re.search(r"가격:\s*([\d,]+)", info)
        ship = re.search(r"배송:\s*(\S+)", info)
        full = f"[{shop.group(1)}] {title}" if shop else title
        d = _make("fmkorea", "https://www.fmkorea.com" + href, full, now, now,
                  price_hint=_num(price.group(1)) if price else None, shipping_hint=ship.group(1) if ship else None)
        if d:
            out.append(d)
    return out


# 에펨코리아는 robots.txt 가 /hotdeal 수집을 금지 → 기본 소스에서 제외 (파서는 남겨 둠)
SOURCES: dict[str, Callable[[datetime], list[Deal]]] = {
    "ppomppu": fetch_ppomppu, "ruliweb": fetch_ruliweb, "clien": fetch_clien, "quasarzone": fetch_quasarzone,
}


def fetch_all(now: Optional[datetime] = None, sources: Optional[dict[str, Callable[[datetime], list[Deal]]]] = None) -> tuple[list[Deal], dict[str, str]]:
    """모든 소스에서 수집. (딜 목록, 소스별 결과 메시지). 한 소스 실패가 다른 소스를 막지 않는다."""
    now = now or datetime.now(timezone.utc)
    deals: dict[str, Deal] = {}
    status: dict[str, str] = {}
    for name, fn in (sources or SOURCES).items():
        try:
            got = fn(now)
            for d in got:
                deals.setdefault(d.url, d)
            status[name] = f"{len(got)}건"
        except Exception as e:  # noqa: BLE001
            status[name] = f"실패: {str(e)[:80]}"
            log.warning("딜 소스 %s 실패: %s", name, str(e)[:120])
    return list(deals.values()), status


def _shop_host(url: str) -> Optional[str]:
    host = (urlparse(url).hostname or "").lower()
    for h in SHOP_HOSTS:
        if host == h or host.endswith("." + h):
            return h
    return None


def _head_location(url: str) -> Optional[str]:
    """단축 링크 1홉 해석 (테스트에서 교체)."""
    r = httpx.head(url, headers={"User-Agent": settings.user_agent}, timeout=8, follow_redirects=False)
    loc = r.headers.get("location")
    return loc if loc and loc.startswith("http") else None


def _is_short(u: str) -> bool:
    host = (urlparse(u).hostname or "").lower()
    return any(host == sh or host.endswith("." + sh) for sh in SHORTENERS)


def _unwrap(u: str, resolve: Callable[[str], Optional[str]]) -> str:
    """리다이렉트 파라미터(…?url=, ruliweb link.php?ol=)와 단축 링크(naver.me 등)를 최대 3홉 풀어 실제 주소로."""
    for _ in range(3):
        qs = parse_qs(urlparse(u).query)
        inner = next((unquote(qs[k][0]) for k in REDIRECT_PARAMS if k in qs and qs[k] and qs[k][0].startswith("http")), None)
        if inner:
            u = inner
            continue
        if _is_short(u):
            nxt = resolve(u)
            if nxt and nxt != u:
                u = nxt
                continue
        break
    return u


HREF_RE = re.compile(r"""href=["']([^"']+)["']""")
TEXT_URL_RE = re.compile(r"""https?://[^\s"'<>]+""")


def find_shop_link(post_html: str, resolve: Callable[[str], Optional[str]] = None) -> Optional[str]:
    """게시글 본문에서 첫 번째 상점 상품 링크. href 우선, 없으면 본문 텍스트의 URL(뽐뿌는 링크가 텍스트로만 있음).
    리다이렉트 래퍼·단축 링크는 풀어서 판단한다."""
    resolve = resolve or _head_location
    hrefs = [html.unescape(h).strip() for h in HREF_RE.findall(post_html)]
    texts = [html.unescape(t).rstrip(".,)\u3002") for t in TEXT_URL_RE.findall(post_html)]
    seen: set[str] = set()
    for raw in hrefs + texts:
        u = "https:" + raw if raw.startswith("//") else raw
        if not u.startswith("http") or u in seen:
            continue
        seen.add(u)
        if _shop_host(u):
            return u.split("#")[0]
        qs = urlparse(u).query
        if any(k + "=" in qs for k in REDIRECT_PARAMS) or _is_short(u):
            u2 = _unwrap(u, resolve)
            if u2 != u and _shop_host(u2):
                return u2.split("#")[0]
    return None


def enrich(deal: Deal, get: Callable[[str], str] = None, resolve: Callable[[str], Optional[str]] = None) -> Deal:
    """게시글 → shop_url → (허용된 상점이면) 정가·판매가 → pct. 실패해도 enriched=True 로 표시해 재시도하지 않는다."""
    get = get or _get
    deal.enriched = True
    try:
        shop = find_shop_link(get(deal.url), resolve)
    except Exception as e:  # noqa: BLE001
        log.debug("게시글 읽기 실패 %s: %s", deal.url, str(e)[:80])
        return deal
    if not shop:
        return deal
    deal.shop_url = shop
    host = (urlparse(shop).hostname or "").lower()
    if any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS) or not allowed(shop):
        return deal
    try:
        q = extract_from_html(get(shop))
    except Exception as e:  # noqa: BLE001
        log.debug("상점 페이지 실패 %s: %s", shop, str(e)[:80])
        return deal
    if not q or (q.currency or "KRW").upper() != (deal.currency or "KRW").upper():   # 해외 상점(USD 등) 가격은 원화 딜과 비교하지 않음
        return deal
    if deal.price is None and q.price:
        deal.price = q.price
    # 근거 가격 = 상점 정가(있으면) 또는 상점 현재 표시가. 딜 가격(쿠폰 적용가)이 그보다 싸면 그만큼이 할인율.
    ref = q.list_price or q.price
    if ref and deal.price and ref > deal.price and deal.price / ref >= MIN_REF_RATIO:   # 65%↓ 초과는 다른 옵션·세트 가격일 가능성이 커 버림
        deal.list_price = ref
        deal.pct = round((ref - deal.price) / ref * 100, 1)
    return deal


def enrich_pending(store, limit: int = ENRICH_PER_RUN, delay: float = ENRICH_DELAY) -> tuple[int, int]:
    """보강 안 된 최신 딜을 limit 건 처리. (처리 수, shop_url 찾은 수)"""
    found = failed = 0
    todo = store.deals_to_enrich(limit)
    for d in todo:
        enrich(d)
        for attempt in range(3):            # Supabase 게이트웨이 504 등 일시 오류는 재시도, 끝내 실패해도 다음 딜로
            try:
                store.update_deal(d)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    failed += 1
                    log.warning("딜 저장 실패(건너뜀) %s: %s", d.url[:60], str(e)[:100])
                else:
                    time.sleep(2 * (attempt + 1))
        found += 1 if d.shop_url else 0
        time.sleep(delay)
    if failed:
        log.warning("딜 보강 저장 실패 %d건 — 다음 실행에서 다시 시도", failed)
    return len(todo), found


def matches_keywords(title: str, keywords: list[str]) -> Optional[str]:
    low = title.lower()
    for k in keywords:
        k = k.strip().lower()
        if k and k in low:
            return k
    return None


def same_key(d: Deal) -> str:
    """여러 커뮤니티에 같은 딜이 올라온 것을 묶는 키: 제목 글자(공백·기호 제거) + 가격. 웹 types.dealKey 와 동일."""
    t = re.sub(r"[^0-9a-z가-힣]", "", d.title.lower())
    return f"{t}|{int(d.price) if d.price else ''}"


def pick_for_digest(deals: list[Deal], keywords: list[str], min_pct: float, limit: int = 10) -> list[tuple[Deal, str]]:
    """다이제스트에 넣을 딜: 관심 키워드 일치 → 할인율 확인 ≥ min_pct 순. 같은 딜(여러 커뮤니티)은 하나만. (딜, 이유)."""
    uniq: dict[str, Deal] = {}
    deals = [d for d in deals if not d.ended]                                     # 끝난 딜은 보내지 않음
    for d in sorted(deals, key=lambda d: (d.below_pct is None, d.posted_at)):   # 시세 확인된 것 우선
        uniq.setdefault(same_key(d), d)
    deals = list(uniq.values())
    out: list[tuple[Deal, str]] = []
    seen: set[str] = set()
    for d in sorted(deals, key=lambda d: d.posted_at, reverse=True):
        k = matches_keywords(d.title, keywords)
        if k and d.url not in seen:
            out.append((d, f"관심 키워드 '{k}'")); seen.add(d.url)
    for d in sorted(deals, key=lambda d: -(d.effective_pct or 0)):
        e = d.effective_pct
        if e is not None and e >= min_pct and d.url not in seen:
            out.append((d, f"평소보다 {e:.0f}% 쌈" if d.below_pct is not None else f"표시 할인 {e:.0f}%")); seen.add(d.url)
    return out[:limit]


def fmt_deal(d: Deal) -> str:
    price = f"{d.price:,.0f}원" if d.price else "가격 미상"
    ship = f" / {d.shipping}" if d.shipping else ""
    if d.below_pct is not None and d.ref_price:
        b = d.below_pct
        pct = f" (평소 {d.ref_price:,.0f}원 대비 ▼{b:.0f}%)" if b > 0 else f" (평소 {d.ref_price:,.0f}원{'보다 비쌈' if b < 0 else ' 수준'})"
    else:
        pct = f" ▼{d.pct:.0f}%" if d.pct is not None else ""
    return f"[{d.site_label or d.site}] {d.title} — {price}{ship}{pct}"


def run_deals(store, now: Optional[datetime] = None) -> int:
    """수집 → 저장(게시글 URL 기준 upsert) → 오래된 것 삭제. 새로 들어간 건수 반환."""
    now = now or datetime.now(timezone.utc)
    fetched, status = fetch_all(now)
    deals = [d for d in fetched if d.title]                      # 제목 없는 것 = 통계 갱신 전용 (루리웹 목록)
    n = store.upsert_deals(deals)
    try:
        store.update_deal_stats([d for d in fetched if d.recommends is not None or d.comments is not None or d.ended])
    except Exception as e:  # noqa: BLE001
        log.warning("딜 추천·종료 갱신 실패: %s", str(e)[:120])
    store.prune_deals(now - timedelta(days=KEEP_DAYS))
    log.info("딜 수집 %d건(신규 %d) — %s", len(deals), n, ", ".join(f"{k} {v}" for k, v in status.items()))
    try:
        done, found = enrich_pending(store)
        log.info("딜 보강 %d건 처리, 상점 링크 %d건", done, found)
    except Exception as e:  # noqa: BLE001
        log.warning("딜 보강 중단(수집분은 저장됨): %s", str(e)[:120])
    try:
        from .market import price_pending
        done, matched = price_pending(store)
        log.info("딜 시세 확인 %d건, 매칭 %d건", done, matched)
    except Exception as e:  # noqa: BLE001
        log.warning("딜 시세 확인 중단: %s", str(e)[:120])
    try:
        from .digest import instant_deal_alerts
        sent = instant_deal_alerts(store, now)
        if sent:
            log.info("큰 딜 즉시 알림 %d건", sent)
    except Exception as e:  # noqa: BLE001
        log.warning("큰 딜 즉시 알림 실패: %s", str(e)[:120])
    return n
