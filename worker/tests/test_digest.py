"""v0.8: 하루 3회 다이제스트 — 저장만 → 모아서 발송 → notified 처리."""
from datetime import datetime, timedelta, timezone

from worker.digest import render_digest, run_digest, slot_label
from worker.models import Alert, PriceSnapshot, Product, UserSettings
from worker.run import _deliver
from worker.storage import SqliteStorage

NOW = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)


def _store(tmp_path):
    return SqliteStorage(tmp_path / "t.db")


def _product(store, title="소니 WH-1000XM6", site="coupang"):
    p = store.add_product(Product("", title, f"mock://{site}/{abs(hash(title))}", site, "KR", "KRW"))
    store.add_snapshot(PriceSnapshot(p.id, 400_000, "KRW", "셀러", True, NOW))
    return p


def test_slot_label_by_kst_hour():
    assert slot_label(datetime(2026, 9, 6, 23, tzinfo=timezone.utc)) == "🌅 아침 알림"   # 08:00 KST
    assert slot_label(datetime(2026, 9, 6, 3, 30, tzinfo=timezone.utc)) == "☀️ 점심 알림"  # 12:30 KST
    assert slot_label(datetime(2026, 9, 6, 10, tzinfo=timezone.utc)) == "🌙 저녁 알림"    # 19:00 KST


def test_deliver_stores_pending_when_digest_on(tmp_path, monkeypatch):
    store = _store(tmp_path)
    p = _product(store)
    sent = []
    monkeypatch.setattr("worker.run.dispatch", lambda *a, **k: (sent.append(1) or ([], [])))
    us = UserSettings(None, digest=True)
    _deliver(store, p, us, Alert(p.id, "drop", 360_000, 400_000, 10.0, None, NOW))
    assert not sent
    pending = store.pending_alerts(None)
    assert len(pending) == 1 and pending[0].notified is False and pending[0].id


def test_deliver_dispatches_immediately_when_digest_off(tmp_path, monkeypatch):
    store = _store(tmp_path)
    p = _product(store)
    sent = []
    monkeypatch.setattr("worker.run.dispatch", lambda *a, **k: (sent.append(1) or ([], [])))
    _deliver(store, p, UserSettings(None, digest=False), Alert(p.id, "drop", 360_000, 400_000, 10.0, None, NOW))
    assert sent and store.pending_alerts(None) == []


def test_target_alert_skips_digest_when_instant(tmp_path, monkeypatch):
    store = _store(tmp_path)
    p = _product(store)
    sent = []
    monkeypatch.setattr("worker.run.dispatch", lambda *a, **k: (sent.append(1) or ([], [])))
    _deliver(store, p, UserSettings(None, digest=True, instant_target=True), Alert(p.id, "target", 360_000, 400_000, 10.0, None, NOW))
    assert sent and store.pending_alerts(None) == []
    _deliver(store, p, UserSettings(None, digest=True, instant_target=False), Alert(p.id, "target", 360_000, 400_000, 10.0, None, NOW))
    assert len(sent) == 1 and len(store.pending_alerts(None)) == 1


def test_render_digest_groups_by_kind_and_dedups_product(tmp_path):
    store = _store(tmp_path)
    a = _product(store, "급락 헤드폰")
    b = _product(store, "목표가 키보드", "11st")
    alerts = [
        Alert(a.id, "drop", 360_000, 400_000, 10.0, None, NOW - timedelta(hours=5)),
        Alert(a.id, "drop", 350_000, 400_000, 12.5, None, NOW - timedelta(hours=1), note="판매자 변경: A → B"),   # 같은 상품·종류 → 최신만
        Alert(b.id, "target", 85_000, 90_000, 5.6, None, NOW - timedelta(hours=2)),
    ]
    title, body, line = render_digest(alerts, {a.id: a, b.id: b}, datetime(2026, 9, 6, 10, tzinfo=timezone.utc))
    assert title == "🌙 저녁 알림 — 새 알림 2건"
    assert line == "목표가 도달 1 · 가격 급락 1"
    assert body.index("[목표가 도달]") < body.index("[가격 급락]")
    assert body.count("급락 헤드폰") == 1 and "350,000원" in body and "판매자 변경" in body


def test_run_digest_sends_and_marks(tmp_path, monkeypatch):
    store = _store(tmp_path)
    p = _product(store)
    _deliver(store, p, UserSettings(None, digest=True), Alert(p.id, "drop", 360_000, 400_000, 10.0, None, NOW))
    calls = []
    monkeypatch.setattr("worker.digest.send_telegram", lambda text, chat_id=None: calls.append(text) or True)
    store.conn.execute("insert into user_settings(user_id,threshold_pct,window_days,notify_email,notify_telegram,notify_push,telegram_chat_id,digest)"
                       " values('local',10,90,0,1,0,'123',1)")
    store.conn.commit()
    assert run_digest(store, now=NOW) == 1
    assert calls and "새 알림 1건" in calls[0]
    assert store.pending_alerts(None) == []
    assert run_digest(store, now=NOW) == 0        # 두 번째는 보낼 게 없음
    assert len(calls) == 1
