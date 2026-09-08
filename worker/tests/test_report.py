"""v0.8: 주간 요약 리포트 — SQLite 저장소로 끝까지."""
from datetime import datetime, timedelta, timezone

from worker.models import Alert, PriceSnapshot, Product
from worker.report import build_report, push_line, render_report
from worker.storage import SqliteStorage

NOW = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
RATES = {"USD": 1350.0}


def _seed(store: SqliteStorage, title: str, site: str, prices, currency="KRW", **kw) -> Product:
    url = f"mock://{site}/{abs(hash(title))}"
    country = "US" if currency == "USD" else "KR"
    p = store.add_product(Product("", title, url, site, country, currency))
    for i, v in enumerate(prices):
        store.add_snapshot(PriceSnapshot(p.id, v, currency, "셀러", True, NOW - timedelta(days=len(prices) - i)))
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _apply(store: SqliteStorage, p: Product) -> None:
    store.conn.execute("update products set target_price=?, risk_level=?, active=?, purchased_at=?, purchased_price=? where id=?",
                       (p.target_price, p.risk_level, int(p.active),
                        p.purchased_at.isoformat() if p.purchased_at else None, p.purchased_price, p.id))
    store.conn.commit()


def test_weekly_report_sections(tmp_path):
    store = SqliteStorage(tmp_path / "t.db")
    drop = _seed(store, "급락 헤드폰", "coupang", [100_000] * 6 + [80_000])                  # -20%
    near = _seed(store, "목표가 근접 마우스", "11st", [50_000] * 6 + [51_000], target_price=50_000)  # +2%
    hit = _seed(store, "목표가 도달 키보드", "11st", [90_000] * 6 + [85_000], target_price=86_000)
    risky = _seed(store, "S급 미러급 가방", "aliexpress", [20, 20, 20, 20], currency="USD", risk_level="high")
    paused = _seed(store, "중단된 상품", "danawa", [10_000] * 4, active=False)
    bought = _seed(store, "구매한 모니터", "coupang", [300_000] * 6, purchased_at=NOW - timedelta(days=2),
                   purchased_price=270_000, active=False)
    for p in (drop, near, hit, risky, paused, bought):
        _apply(store, p)
    store.add_alert(Alert(drop.id, "drop", 80_000, 100_000, 20.0, None, NOW - timedelta(days=1)))
    store.add_alert(Alert(hit.id, "target", 85_000, 90_000, 5.6, None, NOW - timedelta(days=2)))
    store.add_alert(Alert(drop.id, "drop", 80_000, 100_000, 20.0, None, NOW - timedelta(days=20)))   # 7일 밖 → 제외

    rep = build_report(store, None, store.list_products(active_only=False), NOW, RATES)
    assert rep.tracked == 4
    assert rep.alerts == {"drop": 1, "target": 1}
    assert [i.product.title for i in rep.buy_now] == ["급락 헤드폰", "목표가 도달 키보드"]
    assert [i.product.title for i in rep.target_near] == ["목표가 근접 마우스"]
    assert [p.title for p in rep.risk_high] == ["S급 미러급 가방"]
    assert [p.title for p in rep.paused] == ["중단된 상품"]
    assert rep.purchases == 1 and rep.saved_krw == 30_000
    assert not rep.empty

    title, body = render_report(rep)
    assert "8/30~9/6" in title
    assert "알림 2건" in body and "✅ 지금 사도 됨 (2)" in body and "평소보다 20% 싸다" in body
    assert "목표가 도달" in body and "목표가까지 2%" in body
    assert "절약 ≈ 30,000원" in body and "정품 리스크 높음 1개" in body and "추적 중단 1개" in body
    assert "지금 사도 됨 2개" in push_line(rep)


def test_weekly_report_quiet_week(tmp_path):
    store = SqliteStorage(tmp_path / "t.db")
    p = _seed(store, "평범한 상품", "coupang", [10_000] * 5)
    _apply(store, p)
    rep = build_report(store, None, store.list_products(active_only=False), NOW, RATES)
    assert rep.empty
    _, body = render_report(rep)
    assert "조용한 한 주" in body


def test_sales_section_counts_products(tmp_path):
    store = SqliteStorage(tmp_path / "t.db")
    for i in range(3):
        _apply(store, _seed(store, f"알리 상품 {i}", "aliexpress", [10, 10, 10, 10], currency="USD"))
    rep = build_report(store, None, store.list_products(active_only=False), datetime(2026, 11, 1, tzinfo=timezone.utc), RATES)
    assert rep.sales and rep.sales[0][0] == "광군제 11·11" and rep.sales[0][2] == 3
    _, body = render_report(rep)
    assert "광군제 11·11 D-10 — 상품 3개" in body
