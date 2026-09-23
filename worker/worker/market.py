"""시세(평소 가격) — 딜이 '평소보다 정말 싼지' 판단하는 기준가.

커뮤니티 딜은 가격만 있고 비교 기준이 없다. 그래서 새 딜마다 다나와 검색으로 같은 상품을 찾아
**전체 쇼핑몰 현재 최저가**를 관측하고 `market_prices` 에 쌓는다. 평소 가격 = 그 상품(pcode)의 최근 90일 관측 중앙값
(처음엔 관측 1건 = 오늘 최저가, 쌓일수록 진짜 평소 가격). below_pct = (평소 가격 − 딜 가격) / 평소 가격.

- search.danawa.com/dsearch.php 는 robots 허용, Crawl-delay 10 → 요청 간 10초. 실행당 PRICE_PER_RUN 건.
- 가격 이력 그래프(/info/ajax/)는 robots 금지라 쓰지 않는다.
- 오매칭 방지: 제목 토큰 겹침 점수 ≥ MIN_SCORE, 모델명 토큰(숫자+영문)이 있으면 반드시 일치,
  병행/해외/중고/리퍼 등은 딜 제목에도 있을 때만, 딜 가격이 기준가의 35%~130% 범위일 때만(수량·세트 차이 배제).
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

SEARCH_URL = "https://search.danawa.com/dsearch.php"
CRAWL_DELAY = 10.0
PRICE_PER_RUN = 15
USUAL_DAYS = 90
MIN_SCORE = 0.5
RATIO_MIN, RATIO_MAX = 0.35, 1.30

STOP = {"특가", "할인", "무료", "무배", "배송", "무료배송", "정품", "공식", "최저가", "역대가", "역대", "역대최저", "핫딜", "쿠폰", "적용", "카드",
        "행사", "단독", "한정", "세일", "모음", "외", "및", "사은품", "증정", "추가", "선착순", "타임딜", "오늘", "특가전", "기획", "new", "신상"}
CAUTION = ("병행", "해외", "직구", "비공식", "중고", "리퍼", "벌크", "호환", "렌탈", "대여")
MODEL_RE = re.compile(r"^(?=.*\d)(?=.*[a-z])[a-z0-9\-]{3,}$")


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
    pcode: str
    name: str
    url: str
    price: Optional[float]      # 이 상품(색상·옵션 포함) 현재 전체 쇼핑몰 최저가


def parse_search(page: str) -> list[Candidate]:
    """검색 결과의 상품 블록 `<li id="productItem<pcode>" class="prod_item">` 마다 상품명(prod_name)과
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


def _search(query: str) -> str:
    if not allowed(SEARCH_URL):
        raise RuntimeError("robots.txt 금지: 다나와 검색")
    r = httpx.get(SEARCH_URL, params={"query": query}, headers={"User-Agent": settings.user_agent, "Accept-Language": "ko-KR,ko;q=0.9"},
                  timeout=20, follow_redirects=True)
    r.raise_for_status()
    return r.text


def best_match(deal_title: str, deal_price: Optional[float], cands: list[Candidate]) -> Optional[tuple[Candidate, float]]:
    """점수 ≥ MIN_SCORE 이고 가격 비율이 그럴듯한 후보 중, 최고점 −0.1 안의 후보에서 가장 싼 것 (기준가를 보수적으로 낮게)."""
    ok = []
    for c in cands:
        if not c.price:
            continue
        s = match_score(deal_title, c.name)
        if s < MIN_SCORE or (deal_price and not (RATIO_MIN <= deal_price / c.price <= RATIO_MAX)):
            continue
        ok.append((c, s))
    if not ok:
        return None
    top = max(s for _, s in ok)
    return min(((c, s) for c, s in ok if s >= top - 0.1), key=lambda cs: cs[0].price or 1e18)


def usual_price(history: list[float], current: float) -> float:
    """평소 가격 = 최근 관측(오늘 포함) 중앙값."""
    return float(median(history + [current])) if history else current


def price_pending(store, limit: int = PRICE_PER_RUN, delay: float = CRAWL_DELAY,
                  search: Callable[[str], str] = None) -> tuple[int, int]:
    """시세 확인 안 된 최근 딜을 limit 건: 다나와 매칭 → market_prices 적재 → deal.ref_* / below_pct. (처리, 매칭)"""
    search = search or _search
    todo = store.deals_to_price(limit)
    matched = 0
    for i, d in enumerate(todo):
        d.ref_checked = True
        q = query_of(d.title)
        if d.price and q:
            try:
                if i and delay:
                    time.sleep(delay)
                hit = best_match(d.title, d.price, parse_search(search(q)))
            except Exception as e:  # noqa: BLE001
                log.debug("시세 조회 실패 %s: %s", q, str(e)[:80])
                hit = None
            if hit:
                c, _ = hit
                hist = store.market_history(c.pcode, USUAL_DAYS)
                store.add_market_price(c.pcode, c.name, c.price)
                usual = usual_price(hist, c.price)
                d.ref_price, d.ref_name, d.ref_url = usual, c.name, c.url
                d.below_pct = round((usual - d.price) / usual * 100, 1)
                matched += 1
        try:
            store.update_deal(d)
        except Exception as e:  # noqa: BLE001
            log.warning("시세 저장 실패 %s: %s", d.url[:60], str(e)[:100])
    return len(todo), matched
