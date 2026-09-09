"""v0.8 버그 수정 회귀 테스트: suspect 승격 조건, SQLite 중복 등록, 실패 조회의 재조회 간격, 통화 동기화."""
from datetime import datetime, timedelta, timezone

from worker.baseline import all_time_low, confirms_suspect
from worker.models import PriceSnapshot, Product
from worker.run import _due
from worker.storage import SqliteStorage

NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


def _snaps(prices, suspect_last=False):
    out = [PriceSnapshot("p", v, "KRW", "A", True, NOW - timedelta(days=len(prices) - i)) for i, v in enumerate(prices)]
    if suspect_last:
        out[-1].suspect = True
    return out


def test_suspect_confirmed_only_when_repeated():
    hist = _snaps([100_000] * 4 + [10_000], suspect_last=True)      # 파싱 오류로 1/10
    assert confirms_suspect(PriceSnapshot("p", 10_200, "KRW", "A", True, NOW), hist)       # 같은 수준 → 진짜
    assert not confirms_suspect(PriceSnapshot("p", 100_000, "KRW", "A", True, NOW), hist)  # 정상 복귀 → 승격 금지
    assert all_time_low(hist) == 100_000                                                   # suspect 는 역대 최저에서 제외


def test_sqlite_add_product_dedups_null_variant(tmp_path):
    st = SqliteStorage(tmp_path / "t.db")
    a = st.add_product(Product("", "상품", "https://www.amazon.com/dp/B0TEST", "amazon", "US", "USD"))
    b = st.add_product(Product("", "상품", "https://www.amazon.com/dp/B0TEST", "amazon", "US", "USD"))
    assert a.id == b.id and len(st.list_products()) == 1
    c = st.add_product(Product("", "상품", "https://www.amazon.com/dp/B0TEST", "amazon", "US", "USD", variant="th=1"))
    assert c.id != a.id and len(st.list_products()) == 2


def test_failed_fetch_respects_min_interval(tmp_path):
    st = SqliteStorage(tmp_path / "t.db")
    p = st.add_product(Product("", "상품", "https://www.coupang.com/vp/products/1", "coupang", "KR", "KRW"))
    assert _due(p, 6)
    st.mark_fetch(p, "403 Forbidden")
    p2 = st.list_products()[0]
    assert p2.fail_count == 1 and p2.last_fetched_at is not None
    assert not _due(p2, 6)          # 실패 직후 6시간 안엔 다시 두드리지 않음
    assert _due(p2, 0)


def test_worker_adopts_adapter_currency(tmp_path, monkeypatch):
    """generic 사이트(detect_site → USD)인데 페이지가 KRW 를 말하면 products.currency 를 KRW 로."""
    from worker import run as run_mod
    from worker.models import Quote

    class KrwAdapter:
        site = "generic"; min_interval_hours = 0
        def fetch(self, product):
            return Quote(1_590_000, "KRW", title="Apple 제품", seller="Apple")

    monkeypatch.setattr(run_mod, "get_adapter", lambda product: KrwAdapter())
    st = SqliteStorage(tmp_path / "t.db")
    p = st.add_product(Product("", "https://www.apple.com/kr/shop/x", "https://www.apple.com/kr/shop/x", "generic", "US", "USD"))
    run_mod.process_product(st, p, delay=0)
    saved = st.list_products()[0]
    assert saved.currency == "KRW" and saved.title == "Apple 제품"


def test_confirm_suspects_only_same_level(tmp_path):
    """예전 파싱 오류(10,000)와 진짜 세일(55,000)이 둘 다 suspect 일 때, 세일 확정은 세일 수준만 승격한다."""
    st = SqliteStorage(tmp_path / "t.db")
    p = st.add_product(Product("", "상품", "https://www.coupang.com/vp/products/2", "coupang", "KR", "KRW"))
    for i, (price, sus) in enumerate([(100_000, False), (10_000, True), (100_000, False), (55_000, True)]):
        st.add_snapshot(PriceSnapshot(p.id, price, "KRW", "A", True, NOW - timedelta(days=4 - i), suspect=sus))
    st.confirm_suspects(p.id, 54_000)
    hist = st.history(p.id, 30)
    assert [(s.price, s.suspect) for s in hist] == [(100_000, False), (10_000, True), (100_000, False), (55_000, False)]
    assert all_time_low(hist) == 55_000


def test_robots_block_is_manual_only_not_failure(tmp_path, monkeypatch):
    """robots.txt 금지는 실패로 세지 않고(중단 없음), 7일에 한 번만 재확인한다."""
    from worker import run as run_mod
    from worker.adapters.base import AdapterError

    class Blocked:
        site = "coupang"; min_interval_hours = 0
        def fetch(self, product):
            raise AdapterError("robots.txt 가 자동 수집을 금지 — 북마클릿(설정 화면)으로 직접 기록하세요")

    monkeypatch.setattr(run_mod, "get_adapter", lambda product: Blocked())
    st = SqliteStorage(tmp_path / "t.db")
    p = st.add_product(Product("", "마우스", "https://www.coupang.com/vp/products/1", "coupang", "KR", "KRW"))
    for _ in range(12):
        run_mod.process_product(st, st.list_products()[0], delay=0)
    saved = st.list_products(active_only=False)[0]
    assert saved.active and saved.fail_count == 0 and "robots.txt" in (saved.last_error or "")
    assert not run_mod._due(saved, 0)                     # 방금 확인했으니 일주일 뒤에
    assert st.alerts_since(None, NOW - timedelta(days=365)) == []   # paused 알림 없음
