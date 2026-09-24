"""v1.1: 끝난 딜·인기(추천/댓글) 수집과 갱신, 큰 딜 즉시 알림, 쿠팡 시간당 호출 제한."""
from datetime import datetime, timedelta, timezone

from worker import deals as D
from worker import market as M
from worker.digest import instant_deal_alerts, run_digest
from worker.models import Deal, Product
from worker.storage import SqliteStorage

NOW = datetime.now(timezone.utc)

RW_LIST = """<tr class="table_body blocktarget"><td class="subject"><div class="relative"><span style="x">[종료]</span>
<a class="subject_link deco" href="https://bbs.ruliweb.com/market/board/1020/read/107051?"><strong>[쿠팡] PS5</strong>
<a class="num_reply" href="#cmt"> (7)</a></a></td><td class="recomd"> 15 </td></tr>
<tr class="table_body"><td class="subject"><a class="subject_link deco" href="https://bbs.ruliweb.com/market/board/1020/read/107000?"><strong>[옛글]</strong></a></td><td class="recomd"> 3 </td></tr>"""
RW_RSS = """<rss><channel><item><title>[쿠팡] PS5 몬스터헌터 와일즈 / 23,300원</title><link>https://bbs.ruliweb.com/market/board/1020/read/107051</link>
<pubDate>Tue, 08 Sep 2026 19:21:25 +0900</pubDate></item></channel></rss>"""
PP_RSS = """<rss><channel><item><title>[쿠팡] 마우스 (9,900원/무료)</title><link>http://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&amp;no=1</link>
<pubDate>Tue, 08 Sep 2026 11:23:21 GMT</pubDate><hits> [4|1091|12|0]</hits></item>
<item><title>[종료] [지마켓] 헤드폰 (29,000원)</title><link>http://www.ppomppu.co.kr/zboard/view.php?id=ppomppu&amp;no=2</link><pubDate>Tue, 08 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
CL = """<div class="list_item symph_row jirum " data-role="list-row" data-comment-count=6><div class="list_title"><span class="list_subject">
<a href="/service/board/jirum/1?od=T31" data-role="list-title-text"> [네이버] 영양제 (55,940원)</a></span>
<div class="keyword"><span class="view_symph"><span class="list_votes"><i class="fa fa-heart"></i> 9</span></span><span class="icon_info">품절</span></div></div>
<div class="list_time"><span class="timestamp">2026-09-24 10:00:00</span></div></div>"""


def test_source_stats_and_ended(monkeypatch):
    pages = {"rss.php": PP_RSS, "1020/rss": RW_RSS, "board/1020": RW_LIST, "clien": CL}
    monkeypatch.setattr(D, "_get", lambda url: next(v for k, v in pages.items() if k in url))
    pp = D.fetch_ppomppu(NOW)
    assert (pp[0].comments, pp[0].recommends, pp[0].ended) == (4, 12, False) and pp[1].ended
    rw = D.fetch_ruliweb(NOW)
    new = [d for d in rw if d.title]
    assert new[0].recommends == 15 and new[0].comments == 7 and new[0].ended
    stale = [d for d in rw if not d.title]                       # RSS 에서 빠진 옛 글 = 통계 갱신 전용
    assert [d.url for d in stale] == ["https://bbs.ruliweb.com/market/board/1020/read/107000"] and stale[0].recommends == 3
    cl = D.fetch_clien(NOW)
    assert cl[0].recommends == 9 and cl[0].comments == 6 and cl[0].ended


def test_update_stats_keeps_ended_and_digest_skips_ended(tmp_path):
    st = SqliteStorage(tmp_path / "t.db")
    st.upsert_deals([Deal("u1", "ruliweb", "x", "", "헤드폰", 29000, pct=40, posted_at=NOW, fetched_at=NOW)])
    st.update_deal_stats([Deal("u1", "ruliweb", "", "", "", None, recommends=5, comments=2, ended=True)])
    st.update_deal_stats([Deal("u1", "ruliweb", "", "", "", None, recommends=8, ended=False)])      # 종료는 되돌리지 않음
    d = st.list_deals(NOW - timedelta(days=1))[0]
    assert (d.recommends, d.comments, d.ended) == (8, 2, True)
    assert D.pick_for_digest([d], [], 10) == []


def _user(st, telegram=True):
    st.add_product(Product("", "상품", "mock://coupang/x", "coupang", "KR", "KRW"))
    st.conn.execute("insert into user_settings(user_id,threshold_pct,window_days,notify_email,notify_telegram,notify_push,telegram_chat_id,digest,deal_min_pct,deal_keywords)"
                    " values('local',10,90,0,?,0,'123',1,10,'마우스')", (int(telegram),))
    st.conn.commit()


def test_instant_deal_alerts(tmp_path, monkeypatch):
    st = SqliteStorage(tmp_path / "t.db")
    _user(st)
    sent = []
    monkeypatch.setattr("worker.digest.send_telegram", lambda text, chat_id=None: sent.append(text) or True)
    st.upsert_deals([
        Deal("k", "ppomppu", "x", "", "로지텍 마우스", 29900, posted_at=NOW, fetched_at=NOW, ref_price=40000, below_pct=25.2, ref_checked=True),
        Deal("big", "ppomppu", "x", "", "무선 청소기", 99000, posted_at=NOW, fetched_at=NOW, ref_price=200000, below_pct=50.5, ref_checked=True),
        Deal("small", "ppomppu", "x", "", "헤드폰", 90000, posted_at=NOW, fetched_at=NOW, ref_price=100000, below_pct=10.0, ref_checked=True),
        Deal("end", "ppomppu", "x", "", "마우스 패드", 5000, posted_at=NOW, fetched_at=NOW, ref_price=10000, below_pct=50.0, ref_checked=True, ended=True),
    ])
    # SqliteStorage.upsert_deals 는 ref_* 를 넣지 않으므로 직접 반영
    st.conn.execute("update deals set ref_price=40000, below_pct=25.2 where url='k'")
    st.conn.execute("update deals set ref_price=200000, below_pct=50.5 where url='big'")
    st.conn.execute("update deals set ref_price=100000, below_pct=10.0 where url='small'")
    st.conn.execute("update deals set ref_price=10000, below_pct=50.0, ended=1 where url='end'")
    st.conn.commit()
    assert instant_deal_alerts(st, NOW) == 2                      # 키워드+20%↑(마우스) · 키워드 무관 40%↑(청소기). 끝난 딜·10% 는 제외
    assert "청소기" in sent[0] and "로지텍 마우스" in sent[0] and "헤드폰" not in sent[0] and "패드" not in sent[0]
    assert instant_deal_alerts(st, NOW) == 0                      # 다시 보내지 않음
    run_digest(st, now=NOW)
    assert all("로지텍 마우스" not in t for t in sent[1:])        # 다이제스트에도 중복 없음


def test_instant_alert_needs_channel(tmp_path):
    st = SqliteStorage(tmp_path / "t.db")
    _user(st, telegram=False)
    st.upsert_deals([Deal("big", "ppomppu", "x", "", "무선 청소기", 99000, posted_at=NOW, fetched_at=NOW)])
    st.conn.execute("update deals set ref_price=200000, below_pct=50.5 where url='big'"); st.conn.commit()
    assert instant_deal_alerts(st, NOW) == 0 and st.sent_deal_keys(None, NOW - timedelta(days=1)) == set()   # 채널 없으면 기록 안 함 → 다이제스트·앱에서 보게 됨


def test_coupang_only_in_first_20_minutes(monkeypatch):
    cp = [s for s in M.SOURCES if s.name == "coupang"][0]
    import dataclasses
    monkeypatch.setattr(M, "settings", dataclasses.replace(M.settings, coupang_access_key="k", coupang_secret_key="s"))
    monkeypatch.setattr(M, "_now_minute", lambda: 7)
    assert cp.enabled()
    monkeypatch.setattr(M, "_now_minute", lambda: 27)
    assert not cp.enabled()
