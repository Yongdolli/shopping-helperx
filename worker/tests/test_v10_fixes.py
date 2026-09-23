"""v1.0 검토 수정 회귀 테스트: 다이제스트 중복·구멍, 네트워크 끊김 재시도, 해외 통화, 퀘이사존 정규식, 비쌈 표기."""
from datetime import datetime, timedelta, timezone

from worker import deals as D
from worker import market as M
from worker.digest import run_digest
from worker.models import Deal, Product, Quote
from worker.storage import SqliteStorage

NOW = datetime(2026, 9, 24, 10, tzinfo=timezone.utc)   # 19:00 KST


def _deal(url, title, price, hours_ago, **kw):
    return Deal(url, "ppomppu", "x", "", title, price, posted_at=NOW - timedelta(hours=hours_ago), fetched_at=NOW, **kw)


def test_digest_sends_each_deal_once_and_covers_evening(tmp_path, monkeypatch):
    st = SqliteStorage(tmp_path / "t.db")
    st.add_product(Product("", "상품", "mock://coupang/x", "coupang", "KR", "KRW"))
    st.conn.execute("insert into user_settings(user_id,threshold_pct,window_days,notify_email,notify_telegram,notify_push,telegram_chat_id,digest,deal_min_pct)"
                    " values('local',10,90,0,1,0,'123',1,10)")
    st.conn.commit()
    sent = []
    monkeypatch.setattr("worker.digest.send_telegram", lambda text, chat_id=None: sent.append(text) or True)
    # 전날 20시(KST) 에 올라온 딜 = 예전 9시간 창에선 빠지던 구간
    st.upsert_deals([_deal("u1", "로지텍 마우스", 29900, 23, pct=40), _deal("u2", "소니 헤드폰", 99000, 2, pct=30)])
    assert run_digest(st, now=NOW) == 1 and "u1" in sent[0] and "u2" in sent[0]
    assert run_digest(st, now=NOW + timedelta(hours=4.5)) == 0 and len(sent) == 1          # 다음 슬롯에 재발송 없음
    st.upsert_deals([Deal("u3", "ruliweb", "x", "", "로지텍 마우스", 29900, pct=40, posted_at=NOW, fetched_at=NOW)])   # 같은 딜, 다른 커뮤니티
    assert run_digest(st, now=NOW + timedelta(hours=5)) == 0


def test_price_check_retried_when_all_sources_fail(tmp_path):
    st = SqliteStorage(tmp_path / "t.db")
    st.upsert_deals([Deal("u1", "ppomppu", "x", "", "로지텍 G304 무선 마우스", 29900, posted_at=datetime.now(timezone.utc), fetched_at=NOW)])
    src = M.Source("danawa", "", M.parse_danawa, M.best_match, 0, fetcher=lambda q: (_ for _ in ()).throw(RuntimeError("offline")))
    assert M.price_pending(st, sources=[src], sleep=lambda s: None) == (1, 0)
    assert len(st.deals_to_price(10)) == 1                     # 네트워크 끊김 → 확인 안 된 것으로 남음
    ok = M.Source("danawa", "", M.parse_danawa, M.best_match, 0, fetcher=lambda q: "<html></html>")
    M.price_pending(st, sources=[ok], sleep=lambda s: None)
    assert st.deals_to_price(10) == []                         # 응답은 받았고 매칭만 없음 → 확인 완료


def test_enrich_ignores_foreign_currency_shop(monkeypatch):
    monkeypatch.setattr(D, "allowed", lambda url: True)
    monkeypatch.setattr(D, "extract_from_html", lambda html: Quote(45.99, "USD", list_price=59.99))
    d = D.enrich(Deal("https://www.ppomppu.co.kr/zboard/view.php?no=9", "ppomppu", "ebay", "이베이", "헤드폰", None, posted_at=NOW, fetched_at=NOW),
                 lambda url: '<a href="https://www.walmart.com/ip/1">x</a>' if "ppomppu" in url else "<html></html>", lambda u: None)
    assert d.shop_url and d.price is None and d.pct is None


def test_quasarzone_regex_handles_newline_and_trailing_space():
    page = ('<a href="/bbs/qb_saleinfo/views/1"\n            class="subject-link " target="_blank"> [11번가] 모니터 (199,000원/무료) </a>'
            '<span class="v2-list-row__price">￦199,000</span>')
    import worker.deals as mod
    orig = mod._get
    mod._get = lambda url: page
    try:
        got = mod.fetch_quasarzone(NOW)
    finally:
        mod._get = orig
    assert len(got) == 1 and got[0].price == 199000


def test_fmt_deal_pricier_than_usual():
    d = _deal("u", "상품", 11000, 1, ref_price=10000, below_pct=-10.0)
    assert "평소 10,000원보다 비쌈" in D.fmt_deal(d) and "▼-" not in D.fmt_deal(d)
    assert "평소 10,000원 수준" in D.fmt_deal(_deal("u", "상품", 10000, 1, ref_price=10000, below_pct=0.0))
