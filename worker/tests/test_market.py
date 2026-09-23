"""v1.0 시세(평소 가격): 다나와 검색 파싱, 매칭 안전장치, 평소 가격 중앙값, 딜 저장."""
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


def test_price_pending_updates_deal_and_history(tmp_path):
    st = SqliteStorage(tmp_path / "t.db")
    st.upsert_deals([Deal("u1", "ppomppu", "coupang", "쿠팡", "로지텍 G304 무선 마우스", 29900, posted_at=NOW, fetched_at=NOW),
                     Deal("u2", "ppomppu", "etc", "", "모르는 상품", 5000, posted_at=NOW, fetched_at=NOW),
                     Deal("u3", "ppomppu", "etc", "", "가격 없음", None, posted_at=NOW, fetched_at=NOW)])
    st.add_market_price("1", "로지텍 G304", 42000)            # 이전 관측 → 평소 가격 = median(42000, 38900) = 40450
    assert M.price_pending(st, delay=0, search=lambda q: PAGE) == (2, 1)
    by = {d.url: d for d in st.list_deals(NOW - timedelta(days=1))}
    d = by["u1"]
    assert d.ref_checked and d.ref_price == 40450 and d.below_pct == round((40450 - 29900) / 40450 * 100, 1)
    assert d.ref_url.endswith("pcode=1") and d.effective_pct == d.below_pct
    assert by["u2"].ref_checked and by["u2"].below_pct is None
    assert len(st.market_history("1", 90)) == 2
    assert st.deals_to_price(10) == []                       # 가격 없는 딜은 대상 아님, 나머진 처리 완료

    picks = D.pick_for_digest(list(by.values()), [], 10)
    assert [(p.url, why) for p, why in picks] == [("u1", f"평소보다 {d.below_pct:.0f}% 쌈")]
    assert "평소 40,450원 대비" in D.fmt_deal(d)
