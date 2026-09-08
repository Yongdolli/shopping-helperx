"""v0.9 딜 피드: 제목 파싱, 소스 파서(고정 HTML/RSS), 저장소, 다이제스트 선별."""
from datetime import datetime, timedelta, timezone

from worker import deals as D
from worker.digest import render_digest
from worker.models import Deal, Product
from worker.storage import SqliteStorage

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def test_parse_title_variants():
    p = D.parse_title("[롯데온] QCY 무선 블루투스 이어폰 1+1 (29,500원/무료)")
    assert (p.site_label, p.name, p.price, p.shipping, p.pct) == ("롯데온", "QCY 무선 블루투스 이어폰 1+1", 29500, "무료", None)
    p = D.parse_title("[옥션]에디션 센서빌리티 단독특가 청바지(17,420원/3,000원)")
    assert p.site_label == "옥션" and p.price == 17420 and p.shipping == "3,000원"
    p = D.parse_title("[쿠팡] PS5 몬스터헌터 와일즈 / 23,300원")
    assert p.site_label == "쿠팡" and p.name == "PS5 몬스터헌터 와일즈" and p.price == 23300
    p = D.parse_title("[카카오톡선물하기] 투썸플레이스 오벌 티라미수 25% 할인 (26,800원/무료)")
    assert p.pct == 25 and p.price == 26800
    p = D.parse_title("[지마켓] 소니 헤드폰 반값 (219,000원/무배)")
    assert p.pct == 50 and p.shipping == "무료"
    p = D.parse_title("[네이버](PC 스팀)프래그마타 디럭스 에디션 (55,500원/무료)")
    assert p.site_label == "네이버" and p.price == 55500
    p = D.parse_title("[playshop] 플레이스테이션5 Pro 1,298,000원(9일오전11시)")
    assert p.price == 1_298_000
    assert D.site_key("쿠팡") == "coupang" and D.site_key("G마켓") == "gmarket" and D.site_key("네이버멤버쉽") == "naver" and D.site_key("playshop") == "playshop"


PP_RSS = """<?xml version="1.0" encoding="UTF-8" ?><rss><channel>
<item><title>[롯데온] QCY 이어폰 1+1 (29,500원/무료)</title><link>http://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&amp;no=1</link><pubDate>Tue, 08 Sep 2026 11:23:21 GMT</pubDate></item>
<item><title>[쿠팡] 로지텍 G304 마우스 40% 할인 (29,900원/무료)</title><link>http://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&amp;no=2</link><pubDate>Tue, 08 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""
RW_RSS = """<rss><channel><item><title>[쿠팡] PS5 몬스터헌터 와일즈 / 23,300원</title><description><![CDATA[<img src="https://i1.ruliweb.com/t.webp">]]></description><category>게임S/W</category><link>https://bbs.ruliweb.com/market/board/1020/read/107051</link><pubDate>Tue, 08 Sep 2026 19:21:25 +0900</pubDate></item></channel></rss>"""
CL_HTML = """<div class="list_item symph_row jirum " data-role="list-row"><div class="list_title "><span class="list_subject"><a href="/service/board/jirum/19260152?od=T31" data-role="list-title-text"> [네이버멤버쉽] 쏜리서치 투퍼데이 120캡슐 (55,940원)</a></span></div><div class="list_time"><span class="time popover">09-08<span class="timestamp">2026-09-08 20:11:00</span></span></div></div>
<div class="list_item notice"><div class="list_title"><a class="list_subject" href="/service/board/jirum/1">공지</a></div><div class="list_time"></div></div>"""
QZ_HTML = """<div class="v2-list-row"><p class="tit"><a href="/bbs/qb_saleinfo/views/1984678" class="subject-link" target="_blank"> [네이버] 아레나 프라임의자 세일 </a><span class="board-list-comment"></span></p></div><div class="v2-list-row__line3"><div class="v2-list-row__price-group"><span class="v2-list-row__price">￦239,000</span></div></div></div></div>"""
FM_HTML = """<h3 class="title"><a href="/10312873734" class=" hotdeal_var8"><span class="ellipsis-target">끌레도르 바 5종 골라담기</span>&nbsp;</a></h3><div class="hotdeal_info"><span>쇼핑몰: <a class="strong">지마켓</a></span>/<span>가격: <a class="strong">32,990원</a></span>/<span>배송: <a class="strong">무료</a></span></div>"""


def test_source_parsers(monkeypatch):
    pages = {"ppomppu.co.kr": PP_RSS, "ruliweb.com": RW_RSS, "clien.net": CL_HTML, "quasarzone.com": QZ_HTML, "fmkorea.com": FM_HTML}
    monkeypatch.setattr(D, "_get", lambda url: next(v for k, v in pages.items() if k in url))
    pp = D.fetch_ppomppu(NOW)
    assert [d.title for d in pp] == ["QCY 이어폰 1+1", "로지텍 G304 마우스 40% 할인"] and pp[1].pct == 40 and pp[0].site == "lotteon"
    assert pp[0].posted_at.hour == 11
    rw = D.fetch_ruliweb(NOW)
    assert rw[0].site == "coupang" and rw[0].price == 23300 and rw[0].image_url and rw[0].category == "게임S/W"
    cl = D.fetch_clien(NOW)
    assert len(cl) == 1 and cl[0].site == "naver" and cl[0].price == 55940 and cl[0].url.endswith("/19260152")
    qz = D.fetch_quasarzone(NOW)
    assert len(qz) == 1 and qz[0].price == 239000 and qz[0].site == "naver"
    fm = D.fetch_fmkorea(NOW)
    assert len(fm) == 1 and fm[0].site == "gmarket" and fm[0].price == 32990 and fm[0].shipping == "무료"


def test_fetch_all_isolates_failures(monkeypatch):
    ok = lambda now: [Deal("u1", "x", "coupang", "쿠팡", "A", 1000, posted_at=now, fetched_at=now)]  # noqa: E731
    bad = lambda now: (_ for _ in ()).throw(RuntimeError("robots.txt 금지"))  # noqa: E731
    deals, status = D.fetch_all(NOW, {"ok": ok, "bad": bad, "dup": ok})
    assert len(deals) == 1 and status["ok"] == "1건" and status["bad"].startswith("실패") and status["dup"] == "1건"


def test_storage_and_digest_pick(tmp_path):
    st = SqliteStorage(tmp_path / "t.db")
    ds = [Deal("u1", "ppomppu", "coupang", "쿠팡", "로지텍 G304 마우스 40% 할인", 29900, pct=40, posted_at=NOW - timedelta(hours=1), fetched_at=NOW),
          Deal("u2", "clien", "naver", "네이버", "쏜리서치 투퍼데이", 55940, posted_at=NOW - timedelta(hours=2), fetched_at=NOW),
          Deal("u3", "ruliweb", "gmarket", "지마켓", "소니 헤드폰 특가", 219000, pct=20, posted_at=NOW - timedelta(days=10), fetched_at=NOW)]
    assert st.upsert_deals(ds) == 3 and st.upsert_deals(ds) == 0        # 중복 무시
    recent = st.list_deals(NOW - timedelta(hours=9))
    assert [d.url for d in recent] == ["u1", "u2"]
    st.prune_deals(NOW - timedelta(days=7))
    assert len(st.list_deals(NOW - timedelta(days=30))) == 2

    picks = D.pick_for_digest(recent, ["헤드폰", "투퍼데이"], 30)
    assert [(d.url, why) for d, why in picks] == [("u2", "관심 키워드 '투퍼데이'"), ("u1", "표시 할인 40%")]
    assert D.pick_for_digest(recent, [], 50) == []

    title, body, line = render_digest([], {}, datetime(2026, 9, 8, 3, 30, tzinfo=timezone.utc), picks)
    assert title == "☀️ 점심 알림 — 딜 2건" and line == "🔥 딜 2"
    assert "[쿠팡] 로지텍 G304 마우스 40% 할인 — 29,900원 ▼40% · 표시 할인 40%" in body and "u2" in body


def test_run_digest_sends_deals_without_alerts(tmp_path, monkeypatch):
    from worker.digest import run_digest
    st = SqliteStorage(tmp_path / "t.db")
    st.add_product(Product("", "상품", "mock://coupang/x", "coupang", "KR", "KRW"))
    st.upsert_deals([Deal("u1", "ppomppu", "coupang", "쿠팡", "로지텍 마우스 40% 할인", 29900, pct=40, posted_at=NOW - timedelta(hours=1), fetched_at=NOW)])
    st.conn.execute("insert into user_settings(user_id,threshold_pct,window_days,notify_email,notify_telegram,notify_push,telegram_chat_id,digest,deal_min_pct)"
                    " values('local',10,90,0,1,0,'123',1,30)")
    st.conn.commit()
    sent = []
    monkeypatch.setattr("worker.digest.send_telegram", lambda text, chat_id=None: sent.append(text) or True)
    assert run_digest(st, now=NOW) == 1 and "딜 1건" in sent[0]


# ---- 보강: 게시글 → 상점 링크 → 정가
POST = """<div class="body"><a href="https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu">목록</a>
<a href="https://www.ppomppu.co.kr/redirect.php?url=https%3A%2F%2Fwww.gmarket.co.kr%2Fitem%3Fgoodscode%3D123%23tab">상품 링크</a></div>"""
SHOP = """<html><script type="application/ld+json">{"@type":"Product","name":"소니 헤드폰","offers":{"@type":"Offer","price":"219000","priceCurrency":"KRW","availability":"InStock"}}</script>
<meta property="product:original_price:amount" content="439000"></html>"""


def test_find_shop_link_unwraps_redirect():
    none = lambda u: None  # noqa: E731
    assert D.find_shop_link(POST, none) == "https://www.gmarket.co.kr/item?goodscode=123"
    assert D.find_shop_link('<a href="https://www.clien.net/service/board/jirum/1">x</a>', none) is None
    # 루리웹 link.php?ol= (프로토콜 생략 //), 뽐뿌 본문 텍스트 URL, 클리앙 naver.me 단축 링크
    assert D.find_shop_link('<a href="//web.ruliweb.com/link.php?ol=https%3A%2F%2Fwww.coupang.com%2Fvp%2Fproducts%2F857%3FitemId%3D24&bbs=1020">링크</a>', none) == "https://www.coupang.com/vp/products/857?itemId=24"
    assert D.find_shop_link('<td>링크: https://www.lotteon.com/p/product/LM4902370554489</td>', none) == "https://www.lotteon.com/p/product/LM4902370554489"
    fake = lambda u: "https://smartstore.naver.com/shop/products/1" if "naver.me" in u else None  # noqa: E731
    assert D.find_shop_link('<a href="https://naver.me/xaTgPYXr">구매</a>', fake) == "https://smartstore.naver.com/shop/products/1"
    assert D.find_shop_link('<a href="https://naver.me/dead">x</a>', none) is None


def test_make_skips_blind_and_app_posts():
    assert D._make("clien", "u", "블라인드 처리된 글입니다.", NOW, NOW) is None
    assert D._make("clien", "u", "[iOS] 네트워크 모니터 리딤", NOW, NOW) is None
    d = D._make("ppomppu", "http://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&no=1", "[쿠팡] 마우스 (9,900원/무료)", NOW, NOW)
    assert d and d.url.startswith("https://www.ppomppu.co.kr")


def test_enrich_computes_pct_from_list_price(monkeypatch):
    from worker.adapters import jsonld
    monkeypatch.setattr(D, "allowed", lambda url: True)
    monkeypatch.setattr(D, "BLOCKED_HOSTS", ("coupang.com",))   # 테스트에선 지마켓 페이지를 읽는다
    pages = {"ppomppu": POST, "gmarket": SHOP}
    get = lambda url: next(v for k, v in pages.items() if k in url)  # noqa: E731
    q = jsonld.extract_from_html(SHOP)
    assert q and q.price == 219000
    d = D.enrich(Deal("https://www.ppomppu.co.kr/zboard/view.php?no=1", "ppomppu", "gmarket", "지마켓", "소니 헤드폰", 219000, posted_at=NOW, fetched_at=NOW), get, lambda u: None)
    assert d.enriched and d.shop_url == "https://www.gmarket.co.kr/item?goodscode=123"
    assert d.pct is None                       # 딜 가격 == 상점 표시가 → 할인 근거 없음
    d = D.enrich(Deal("https://www.ppomppu.co.kr/zboard/view.php?no=2", "ppomppu", "gmarket", "지마켓", "소니 헤드폰", 175200, posted_at=NOW, fetched_at=NOW), get, lambda u: None)
    assert d.list_price == 219000 and d.pct == 20.0   # 쿠폰가가 상점 표시가보다 20% 싸다


def test_enrich_skips_blocked_shop_but_keeps_link(monkeypatch):
    calls = []
    get = lambda url: calls.append(url) or '<a href="https://www.coupang.com/vp/products/1">쿠팡</a>'  # noqa: E731
    d = D.enrich(Deal("https://www.clien.net/service/board/jirum/1", "clien", "coupang", "쿠팡", "마우스", 29900, posted_at=NOW, fetched_at=NOW), get, lambda u: None)
    assert d.shop_url == "https://www.coupang.com/vp/products/1" and d.enriched and d.pct is None and len(calls) == 1


def test_enrich_pending_marks_and_updates(tmp_path, monkeypatch):
    st = SqliteStorage(tmp_path / "t.db")
    st.upsert_deals([Deal("https://www.clien.net/service/board/jirum/1", "clien", "gmarket", "지마켓", "A", 1000, posted_at=NOW, fetched_at=NOW)])
    monkeypatch.setattr(D, "_get", lambda url: '<a href="https://www.gmarket.co.kr/item?goodscode=9">x</a>' if "clien" in url else "<html></html>")
    monkeypatch.setattr(D, "allowed", lambda url: True)
    monkeypatch.setattr(D, "_head_location", lambda url: None)
    assert st.deals_to_enrich(10)[0].enriched is False
    assert D.enrich_pending(st, delay=0) == (1, 1)
    d = st.list_deals(NOW - timedelta(days=1))[0]
    assert d.enriched and d.shop_url == "https://www.gmarket.co.kr/item?goodscode=9"
    assert st.deals_to_enrich(10) == []


def test_enrich_pending_retries_store_failures(tmp_path, monkeypatch):
    """Supabase 504 같은 일시 오류: 재시도 후 성공하거나, 끝내 실패해도 다음 딜로 넘어간다."""
    st = SqliteStorage(tmp_path / "t.db")
    st.upsert_deals([Deal(f"https://www.clien.net/service/board/jirum/{i}", "clien", "x", "x", f"A{i}", 1000, posted_at=NOW, fetched_at=NOW) for i in range(2)])
    monkeypatch.setattr(D, "_get", lambda url: "<html></html>")
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    calls = {"n": 0}
    real = st.update_deal
    def flaky(d):
        calls["n"] += 1
        if calls["n"] <= 4:          # 첫 딜: 3번 모두 실패 → 건너뜀, 둘째 딜: 1번 실패 후 성공
            raise RuntimeError("Gateway Timeout")
        real(d)
    monkeypatch.setattr(st, "update_deal", flaky)
    assert D.enrich_pending(st, delay=0) == (2, 0)
    assert len(st.deals_to_enrich(10)) == 1       # 실패한 첫 딜만 남아 다음 실행에서 재시도
