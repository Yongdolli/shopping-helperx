"""시세(평소 가격) — 딜이 '평소보다 정말 싼지' 판단하는 기준가. 여러 사이트에서 같은 상품을 찾아 비교한다.

커뮤니티 딜은 가격만 있고 비교 기준이 없다. 그래서 새 딜마다 아래 소스에서 같은 상품을 찾아 시세를 관측하고
`market_prices`(key = "<소스>:<상품 id>")에 쌓는다.

  소스      | 값                                   | robots / 간격
  다나와    | 전체 쇼핑몰 현재 최저가 (옵션·색상 중 최저) | 허용, Crawl-delay 10초
  에누리    | 전체 쇼핑몰 현재 최저가 (JSON-LD lowPrice)  | 허용, 2초
  옥션      | 조건에 맞는 판매글 가격들의 중앙값 (≥3건)  | 허용, 2초
  쿠팡      | 파트너스 Open API 검색 결과 최저가        | 공식 API, 키 있을 때만, 실행당 5회 (시간당 ~10회 제한)
  (네이버·지마켓·SSG·롯데온, 그리고 쿠팡 웹페이지는 robots 금지·차단으로 사용 불가 — 2026-09 실측)

소스별 평소 가격 = 그 키의 최근 90일 관측 중앙값(오늘 포함). 딜의 평소 가격 = 소스별 평소 가격들의 중앙값.
below_pct = (평소 가격 − 딜 가격) / 평소 가격. ref_name 에 근거("다나와 38,900 · 에누리 46,270 · 옥션 48,730")를 붙인다.

오매칭 방지: 제목 토큰 점수 ≥ MIN_SCORE, 모델명 토큰은 정확 일치(G304 ≠ G304rWH), 병행/해외/비공식/중고 등은 딜도 그럴 때만,
개수·용량·무게가 둘 다 적혀 있으면 일치(48팩≠24개), 딜 가격이 기준가의 35%~130%, 최고점 −0.1 안의 후보 중 가장 싼 것(보수적).
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
from dataclasses import dataclass
from statistics import median
from typing import Callable, Optional

import httpx

from .config import settings
from .robots import allowed

log = logging.getLogger(__name__)

PRICE_PER_RUN = 15
USUAL_DAYS = 90
MIN_SCORE = 0.5
RATIO_MIN, RATIO_MAX = 0.35, 1.30
AUCTION_MIN_LISTINGS = 3

STOP = {"특가", "할인", "무료", "무배", "배송", "무료배송", "정품", "공식", "최저가", "역대가", "역대", "역대최저", "핫딜", "쿠폰", "적용", "카드",
        "행사", "단독", "한정", "세일", "모음", "외", "및", "사은품", "증정", "추가", "선착순", "타임딜", "오늘", "특가전", "기획", "new", "신상",
        "당일발송", "당일출고", "국내발송", "인증점", "공식인증", "판매점"}
CAUTION = ("병행", "해외", "직구", "비공식", "중고", "리퍼", "벌크", "호환", "렌탈", "대여")
MODEL_RE = re.compile(r"^(?=.*\d)(?=.*[a-z])[a-z0-9\-]{3,}$")
LABEL = {"danawa": "다나와", "enuri": "에누리", "auction": "옥션", "coupang": "쿠팡"}

# 수량 가드: 개수·용량·무게가 둘 다 적혀 있으면 같은 값이 하나는 있어야 한다 (48팩 ≠ 24개, 64봉 ≠ 16봉)
QTY_RE = re.compile(r"(?:x|×|\*)\s*(\d+)|(\d+(?:\.\d+)?)\s*(개입|개|팩|입|병|캔|봉|매|구|롤|ea|kg|g|ml|l|리터)(?![a-z가-힣])")
QTY_UNIT = {"개입": ("n", 1), "개": ("n", 1), "팩": ("n", 1), "입": ("n", 1), "병": ("n", 1), "캔": ("n", 1), "봉": ("n", 1), "매": ("n", 1),
            "구": ("n", 1), "롤": ("n", 1), "ea": ("n", 1), "kg": ("g", 1000), "g": ("g", 1), "ml": ("ml", 1), "l": ("ml", 1000), "리터": ("ml", 1000)}


def quantities(text: str) -> dict[str, set[float]]:
    out: dict[str, set[float]] = {}
    for x, num, unit in QTY_RE.findall(html.unescape(text).lower().replace(",", "")):
        kind, mul = ("n", 1) if x else QTY_UNIT[unit]
        out.setdefault(kind, set()).add(round(float(x or num) * mul, 3))
    return out


def qty_compatible(deal_title: str, cand_name: str) -> bool:
    dq, cq = quantities(deal_title), quantities(cand_name)
    return all(dq[k] & cq[k] for k in dq.keys() & cq.keys())


def tokens(text: str, keep_single: bool = False) -> list[str]:
    t = html.unescape(text).lower()
    t = re.sub(r"[\[【].*?[\]】]", " ", t)                        # [사이트]
    t = re.sub(r"\d[\d,]*\s*원", " ", t)                          # 가격
    t = re.sub(r"\d+\s*\+\s*\d+", " ", t)                         # 1+1
    out = []
    for w in re.findall(r"[0-9a-z가-힣\-]+", t):
        w = w.strip("-")
        if not w or (len(w) < 2 and not w.isdigit() and not keep_single):
            continue
        if w in STOP:
            continue
        out.append(w)
    return out


def query_of(title: str, n: int = 6) -> str:
    return " ".join(tokens(title)[:n])


def match_score(deal_title: str, cand_name: str) -> float:
    """0.7 × (딜 토큰이 후보에 있는 비율) + 0.3 × (후보 토큰이 딜에 있는 비율).
    모델명 토큰(영문+숫자)은 토큰 단위로 정확히 같아야 하고(G304 ≠ G304rWH), 병행/해외/중고 등은 딜에도 있어야 한다."""
    dt = tokens(deal_title)
    ct = tokens(cand_name, keep_single=True)
    if not dt or not ct:
        return 0.0
    if any(c in cand_name for c in CAUTION) and not any(c in deal_title for c in CAUTION):
        return 0.0                                              # 병행·해외·중고 상품은 딜도 그런 상품일 때만
    if not qty_compatible(deal_title, cand_name):
        return 0.0
    cset = {w.replace("-", "") for w in ct}
    cn = " ".join(ct)
    for w in dt:
        if MODEL_RE.match(w) and w.replace("-", "") not in cset:
            return 0.0
    dtext = " ".join(dt)
    cover = sum(1 for w in dt if (w.replace("-", "") in cset if MODEL_RE.match(w) else w in cn)) / len(dt)
    prec = sum(1 for w in ct if w in dtext) / len(ct)
    return round(0.7 * cover + 0.3 * prec, 3)


@dataclass
class Candidate:
    pcode: str                  # 소스 안에서의 상품/판매글 id
    name: str
    url: str
    price: Optional[float]      # 다나와·에누리: 현재 전체 쇼핑몰 최저가 / 옥션: 판매글 가격


# ---------------------------------------------------------------- 파서 (순수 함수, 테스트 대상)
def parse_search(page: str) -> list[Candidate]:
    """다나와 검색 결과의 상품 블록 `<li id="productItem<pcode>" class="prod_item">` 마다 상품명(prod_name)과
    옵션·색상별 가격(price_sect) 중 최저를 현재 전체 쇼핑몰 최저가로."""
    out: list[Candidate] = []
    marks = list(re.finditer(r'id="productItem(\d+)"', page))
    for k, m in enumerate(marks):
        pcode = m.group(1)
        seg = page[m.start(): marks[k + 1].start() if k + 1 < len(marks) else m.start() + 60000]
        nm = re.search(r'<p class="prod_name">\s*<a[^>]*>(.*?)</a>', seg, re.S)
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(nm.group(1)))).strip() if nm else ""
        bundle = re.search(r'wishListBundleVal_\d+"\s+value="([^"]*)"', seg)       # "병행수입^pcode**해외구매^…//이름//pcode"
        labels = html.unescape(bundle.group(1)).split("//")[0] if bundle else ""
        name += "".join(f" ({c})" for c in CAUTION if c in labels and c not in name)
        if not name or any(c.pcode == pcode for c in out):
            continue
        prices = [float(p.replace(",", "")) for p in re.findall(r'class="price_sect">\s*<a[^>]*>\s*<strong>([\d,]{3,})</strong>', seg)]
        out.append(Candidate(pcode, name, f"https://prod.danawa.com/info/?pcode={pcode}", min(prices) if prices else None))
    return out


parse_danawa = parse_search


def parse_enuri(page: str) -> list[Candidate]:
    """에누리 검색 결과의 JSON-LD ItemList: Product(name, sku, url, offers.lowPrice)."""
    out: list[Candidate] = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for el in data.get("itemListElement", []) if isinstance(data, dict) else []:
            it = el.get("item") or {}
            offers = it.get("offers") or {}
            low = offers.get("lowPrice") or offers.get("price")
            if not it.get("name") or not low:
                continue
            sku = str(it.get("sku") or re.sub(r"\D", "", it.get("url", "")) or it["name"])
            out.append(Candidate(sku, html.unescape(it["name"]), it.get("url") or "", float(low)))
    return out


def parse_auction(page: str) -> list[Candidate]:
    """옥션 검색 결과 __NEXT_DATA__ 의 판매글(item.text, price.price.text). 광고 모듈(clickUrl 이 cpc)은 제외."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        modules = data["props"]["pageProps"]["initialStates"]["curatorData"]["regionsData"]["content"]["modules"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    out: list[Candidate] = []
    for mod in modules:
        for row in mod.get("rows") or []:
            vm = row.get("viewModel") if isinstance(row, dict) else None
            if not isinstance(vm, dict) or not isinstance(vm.get("item"), dict) or not isinstance(vm.get("price"), dict):
                continue
            if "/cpc/" in str(vm.get("clickUrl", "")):
                continue
            text = (vm["item"].get("text") or "").strip()
            ptxt = ((vm["price"].get("price") or {}).get("text") or vm["price"].get("binPrice") or "")
            try:
                price = float(str(ptxt).replace(",", ""))
            except ValueError:
                continue
            if text and price > 0:
                out.append(Candidate(str(vm.get("itemNo") or text), text, vm["item"].get("link") or "", price))
    return out


def parse_coupang(body: str) -> list[Candidate]:
    """쿠팡 파트너스 검색 API 응답 JSON: data.productData[] (productId, productName, productPrice, productUrl)."""
    try:
        d = json.loads(body)
    except json.JSONDecodeError:
        return []
    items = ((d.get("data") or {}).get("productData") or []) if isinstance(d, dict) else []
    out = []
    for it in items:
        try:
            out.append(Candidate(str(it["productId"]), it.get("productName") or "", it.get("productUrl") or "", float(it["productPrice"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _coupang_search(query: str) -> str:
    from urllib.parse import urlencode
    from .adapters.coupang import DOMAIN, SEARCH_PATH, sign
    qs = urlencode({"keyword": query[:60], "limit": 20})
    auth = sign("GET", SEARCH_PATH, qs, settings.coupang_access_key, settings.coupang_secret_key)
    r = httpx.get(f"{DOMAIN}{SEARCH_PATH}?{qs}", headers={"Authorization": auth}, timeout=20)
    if r.status_code == 403:
        raise RuntimeError("쿠팡 403 — 호출 제한 또는 키 오류")
    r.raise_for_status()
    return r.text


# ---------------------------------------------------------------- 매칭
def best_match(deal_title: str, deal_price: Optional[float], cands: list[Candidate]) -> Optional[tuple[Candidate, float]]:
    """점수 ≥ MIN_SCORE 이고 가격 비율이 그럴듯한 후보 중, 최고점 −0.1 안의 후보에서 가장 싼 것 (기준가를 보수적으로 낮게)."""
    ok = _valid(deal_title, deal_price, cands)
    if not ok:
        return None
    top = max(s for _, s in ok)
    return min(((c, s) for c, s in ok if s >= top - 0.1), key=lambda cs: cs[0].price or 1e18)


def _valid(deal_title: str, deal_price: Optional[float], cands: list[Candidate]) -> list[tuple[Candidate, float]]:
    ok = []
    for c in cands:
        if not c.price:
            continue
        s = match_score(deal_title, c.name)
        if s < MIN_SCORE or (deal_price and not (RATIO_MIN <= deal_price / c.price <= RATIO_MAX)):
            continue
        ok.append((c, s))
    return ok


def listing_median(deal_title: str, deal_price: Optional[float], cands: list[Candidate],
                   min_n: int = AUCTION_MIN_LISTINGS) -> Optional[tuple[Candidate, float]]:
    """오픈마켓 판매글: 조건에 맞는 판매글 가격의 중앙값 (흔히 팔리는 가격). 대표 이름은 최고점 판매글."""
    ok = _valid(deal_title, deal_price, cands)
    if len(ok) < min_n:
        return None
    best = max(ok, key=lambda cs: cs[1])
    return Candidate(best[0].pcode, best[0].name, best[0].url, float(median(c.price for c, _ in ok))), best[1]


# ---------------------------------------------------------------- 소스
@dataclass
class Source:
    name: str
    url: str                                            # 검색 URL, {q} 자리에 검색어
    parse: Callable[[str], list[Candidate]]
    pick: Callable[..., Optional[tuple[Candidate, float]]]
    delay: float                                        # 같은 소스 요청 간 최소 간격(초)
    param: Optional[str] = None                         # GET 파라미터 이름
    fetcher: Optional[Callable[[str], str]] = None      # 검색어 → 응답 본문 (API 소스)
    budget: int = 0                                     # 실행당 호출 상한 (0 = 무제한)
    enabled: Callable[[], bool] = lambda: True


SOURCES: list[Source] = [
    Source("danawa", "https://search.danawa.com/dsearch.php", parse_danawa, best_match, 10.0, "query"),
    Source("enuri", "https://www.enuri.com/search.jsp", parse_enuri, best_match, 2.0, "keyword"),
    Source("auction", "https://browse.auction.co.kr/search", parse_auction, listing_median, 2.0, "keyword"),
    Source("coupang", "https://api-gateway.coupang.com", parse_coupang, best_match, 6.0, fetcher=_coupang_search, budget=5,
           enabled=lambda: bool(settings.coupang_access_key and settings.coupang_secret_key)),
]


def _fetch(src: Source, query: str) -> str:
    if src.fetcher:                                             # 공식 API (robots 대상 아님)
        return src.fetcher(query)
    if not allowed(src.url):
        raise RuntimeError(f"robots.txt 금지: {src.name}")
    for attempt in range(2):                                    # 일시 오류(타임아웃·5xx) 1회 재시도
        try:
            r = httpx.get(src.url, params={src.param: query}, timeout=20, follow_redirects=True,
                          headers={"User-Agent": settings.user_agent, "Accept-Language": "ko-KR,ko;q=0.9"})
            r.raise_for_status()
            return r.text
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def usual_price(history: list[float], current: float) -> float:
    """평소 가격 = 최근 관측(오늘 포함) 중앙값."""
    return float(median(history + [current])) if history else current


def price_pending(store, limit: int = PRICE_PER_RUN, sources: Optional[list[Source]] = None,
                  fetch: Callable[[Source, str], str] = None, sleep: Callable[[float], None] = time.sleep) -> tuple[int, int]:
    """시세 확인 안 된 최근 딜을 limit 건: 소스마다 매칭 → market_prices 적재 → deal.ref_* / below_pct. (처리, 매칭)"""
    sources = sources if sources is not None else SOURCES
    fetch = fetch or _fetch
    sources = [s for s in sources if s.enabled()]
    last: dict[str, float] = {}
    used: dict[str, int] = {}
    todo = store.deals_to_price(limit)
    matched = 0
    for d in todo:
        d.ref_checked = True
        q = query_of(d.title)
        found: list[tuple[Source, Candidate, float, float]] = []          # (소스, 후보, 점수, 소스별 평소 가격)
        if d.price and q:
            for src in sources:
                if src.budget and used.get(src.name, 0) >= src.budget:
                    continue
                used[src.name] = used.get(src.name, 0) + 1
                wait = src.delay - (time.monotonic() - last.get(src.name, -1e9))
                if wait > 0:
                    sleep(wait)
                last[src.name] = time.monotonic()
                try:
                    hit = src.pick(d.title, d.price, src.parse(fetch(src, q)))
                except Exception as e:  # noqa: BLE001 — 한 소스 실패가 다른 소스를 막지 않는다
                    log.debug("시세 조회 실패 %s %s: %s", src.name, q, str(e)[:80])
                    continue
                if not hit:
                    continue
                c, score = hit
                key = f"{src.name}:{c.pcode}"
                hist = store.market_history(key, USUAL_DAYS)
                store.add_market_price(key, c.name, c.price)
                found.append((src, c, score, usual_price(hist, c.price)))
        if found:
            usual = float(median(u for *_, u in found))
            best = max(found, key=lambda f: (f[2], f[0].name != "auction"))    # 점수 높은 것, 같으면 가격비교 사이트
            link = next((c.url for s, c, _, _ in found if s.name in ("danawa", "enuri", "coupang") and c.url), best[1].url)
            d.ref_price = usual
            d.ref_name = f"{best[1].name} ({' · '.join(f'{LABEL[s.name]} {u:,.0f}' for s, _, _, u in found)})"[:300]
            d.ref_url = link
            d.below_pct = round((usual - d.price) / usual * 100, 1)
            matched += 1
        try:
            store.update_deal(d)
        except Exception as e:  # noqa: BLE001
            log.warning("시세 저장 실패 %s: %s", d.url[:60], str(e)[:100])
    return len(todo), matched
