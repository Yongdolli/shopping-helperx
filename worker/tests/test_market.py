"""v1.0 시세(평소 가격): 다나와 검색 파싱, 매칭 안전장치, 평소 가격 중앙값, 딜 저장."""
import json
from datetime import datetime, timedelta, timezone

from worker import deals as D
from worker import market as M
from worker.models import Deal
from worker.storage import SqliteStorage

NOW = datetime.now(timezone.utc)


def _item(pcode: str, name: str, prices: list[str], labels: str = "블랙") -> str:
    rows = "".join(f'<p class="price_sect"> <a href="x"><strong>{p}</strong>원</a></p>' for p in prices)
    return (f'<li id="productItem{pcode}" class="prod_item"><p class="prod_name"> <a href="x"><b>{name.split()[0]}</b> {" ".join(name.split()[1:])}</a></p>'
            f'<input type="hidden" id="wishListBundleVal_{pcode}" value="{labels}^{pcode}//{name}//{pcode}" />'
            f'<div class="prod_pricelist">{rows}</div></li>')


PAGE = "<ul>" + "".join([
    _item("1", "로지텍 G304 LIGHTSPEED WIRELESS (정품)", ["46,060", "38,900"]),
    _item("2", "로지텍 G304 LIGHTSPEED WIRELESS", ["30,080"], labels="병행수입^2**해외구매"),
    _item("3", "로지텍 G G304rWH LIGHTSPEED 게이밍 마우스 (정품)", ["59,900"]),
    _item("4", "로지텍 G304 X SUPERLIGHT", ["1,800"]),
    _item("5", "타이거게이밍 마우스 피트 로지텍", ["6,400"]),
]) + "</ul>"


def test_parse_search_blocks():
    c = M.parse_search(PAGE)
    assert [(x.pcode, x.price) for x in c] == [("1", 38900), ("2", 30080), ("3", 59900), ("4", 1800), ("5", 6400)]
    assert "(병행)" in c[1].name and "(해외)" in c[1].name


def test_best_match_guards():
    c = M.parse_search(PAGE)
    hit = M.best_match("[쿠팡] 로지텍 G304 무선 마우스 (29,900원/무료)", 29900, c)
    assert hit and hit[0].pcode == "1"                       # 정품 (병행·G304rWH·1,800원 이상치·마우스피트 제외)
    assert M.match_score("로지텍 G304 마우스", "로지텍 G G304rWH 마우스") == 0.0     # 모델명은 토큰 단위 일치
    assert M.best_match("로지텍 G304 병행", 25000, c)[0].pcode == "2"              # 병행 딜은 병행 상품과
    assert M.best_match("삼성 갤럭시 버즈3", 99000, c) is None


def test_usual_price_median():
    assert M.usual_price([], 38900) == 38900
    assert M.usual_price([40000, 42000, 41000, 30000], 39000) == 40000


ENURI = """<script type="application/ld+json">{"itemListElement":[
 {"item":{"offers":{"lowPrice":41000,"offerCount":283,"@type":"AggregateOffer"},"@type":"Product","name":"로지텍 G304 LIGHTSPEED WIRELESS (정품)","sku":"28073619","url":"https://www.enuri.com/detail.jsp?modelno=28073619"},"@type":"ListItem"},
 {"item":{"offers":{"lowPrice":1800},"@type":"Product","name":"로지텍 G304 X SUPERLIGHT","sku":"147098573","url":"https://www.enuri.com/detail.jsp?modelno=147098573"},"@type":"ListItem"}]}</script>"""


def _auction(rows):
    mods = [{"rows": [{"viewModel": {"itemNo": f"A{i}", "item": {"text": t, "link": f"http://itempage3.auction.co.kr/DetailView.aspx?itemno=A{i}"},
                                      "price": {"price": {"text": p}}, **({"clickUrl": "http://ats.auction.co.kr/cpc/clk?x"} if ad else {})}}
                       for i, (t, p, ad) in enumerate(rows)]}]
    data = {"props": {"pageProps": {"initialStates": {"curatorData": {"regionsData": {"content": {"modules": mods}}}}}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>'


AUCTION = _auction([("로지텍 G304 LIGHTSPEED 무선 마우스", "43,000", False), ("로지텍코리아 G304 LIGHTSPEED 무선 게이밍 마우스", "45,000", False),
                    ("로지텍 G304 무선 마우스 블랙", "47,000", False), ("로지텍 G304 무선 마우스 광고", "10,000", True),
                    ("로지텍 G304 무선 마우스 병행", "30,000", False), ("로지텍 마우스 패드", "9,000", False)])


def test_parse_enuri_and_auction():
    e = M.parse_enuri(ENURI)
    assert [(c.pcode, c.price) for c in e] == [("28073619", 41000), ("147098573", 1800)]
    a = M.parse_auction(AUCTION)
    assert len(a) == 5 and all(c.price != 10000 for c in a)        # 광고(cpc) 제외
    hit = M.listing_median("[쿠팡] 로지텍 G304 무선 마우스", 29900, a)
    assert hit and hit[0].price == 45000                           # 병행·패드 제외 3건(43k·45k·47k)의 중앙값
    assert M.listing_median("로지텍 G304 무선 마우스", 29900, a[:2]) is None   # 3건 미만이면 안 씀


def test_price_pending_multi_source(tmp_path):
    st = SqliteStorage(tmp_path / "t.db")
    st.upsert_deals([Deal("u1", "ppomppu", "coupang", "쿠팡", "로지텍 G304 무선 마우스", 29900, posted_at=NOW, fetched_at=NOW),
                     Deal("u2", "ppomppu", "etc", "", "모르는 상품", 5000, posted_at=NOW, fetched_at=NOW),
                     Deal("u3", "ppomppu", "etc", "", "가격 없음", None, posted_at=NOW, fetched_at=NOW)])
    st.add_market_price("danawa:1", "로지텍 G304", 42000)          # 이전 관측 → 다나와 평소 = median(42000, 38900) = 40450
    pages = {"danawa": PAGE, "enuri": ENURI, "auction": AUCTION}
    fails = {"n": 0}
    def fetch(src, q):
        if src.name == "enuri" and "모르는" in q:
            fails["n"] += 1
            raise RuntimeError("timeout")                          # 한 소스 실패는 건너뜀
        return pages[src.name]
    assert M.price_pending(st, fetch=fetch, sleep=lambda s: None) == (2, 1)
    by = {d.url: d for d in st.list_deals(NOW - timedelta(days=1))}
    d = by["u1"]
    assert d.ref_checked and d.ref_price == 41000                  # median(다나와 40450, 에누리 41000, 옥션 45000)
    assert d.below_pct == round((41000 - 29900) / 41000 * 100, 1) and d.effective_pct == d.below_pct
    assert "다나와 40,450" in d.ref_name and "에누리 41,000" in d.ref_name and "옥션 45,000" in d.ref_name
    assert d.ref_url.startswith("https://prod.danawa.com") or d.ref_url.startswith("https://www.enuri.com")
    assert by["u2"].ref_checked and by["u2"].below_pct is None and fails["n"] == 1
    assert len(st.market_history("danawa:1", 90)) == 2 and len(st.market_history("enuri:28073619", 90)) == 1
    assert st.deals_to_price(10) == []

    picks = D.pick_for_digest(list(by.values()), [], 10)
    assert [(p.url, why) for p, why in picks] == [("u1", f"평소보다 {d.below_pct:.0f}% 쌈")]
    assert "평소 41,000원 대비" in D.fmt_deal(d)


def test_quantity_guard():
    assert M.quantities("매일두유 검은콩 190ml 48팩") == {"ml": {190.0}, "n": {48.0}}
    assert M.quantities("퍼실 세탁세제 2L 6개") == {"ml": {2000.0}, "n": {6.0}}
    assert M.quantities("햇반 작은공기 130g x36") == {"g": {130.0}, "n": {36.0}}
    assert not M.qty_compatible("매일두유 검은콩 190ml 48팩", "매일유업 매일두유 검은콩 190ml (24개)")
    assert M.qty_compatible("퍼실 라벤더 세탁세제 2L 6개", "퍼실 라벤더 젤 2L (6개)")
    assert M.qty_compatible("로지텍 G304 무선 마우스", "로지텍 G304 LIGHTSPEED 3개입")       # 한쪽만 있으면 통과
    assert M.match_score("광천김 도시락김 4g 64봉", "광천김 도시락김 4g 16봉") == 0.0
