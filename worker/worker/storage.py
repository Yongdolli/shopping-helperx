"""저장소: SQLite(개발) / Supabase(운영). 같은 인터페이스."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol

from .config import settings
from .models import Alert, PriceSnapshot, Product, PushSubscription, UserSettings


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _default_settings(user_id: Optional[str]) -> UserSettings:
    return UserSettings(user_id, settings.threshold_pct, settings.window_days,
                        bool(settings.alert_email_to), bool(settings.telegram_chat_id), True,
                        settings.alert_email_to or None, settings.telegram_chat_id or None, settings.digest, True)


class Storage(Protocol):
    def list_products(self, active_only: bool = True) -> list[Product]: ...
    def add_product(self, p: Product) -> Product: ...
    def update_product(self, p: Product) -> None: ...
    def mark_fetch(self, p: Product, error: Optional[str]) -> None: ...
    def update_risk(self, p: Product, level: str, reasons: str) -> None: ...
    def latest_prices_by_model(self, model_no: str, currency: str, exclude_id: str) -> list[float]: ...
    def history(self, product_id: str, days: int) -> list[PriceSnapshot]: ...
    def add_snapshot(self, s: PriceSnapshot) -> None: ...
    def confirm_suspects(self, product_id: str, price: float) -> None: ...   # price ±5% 의 suspect 만 승격
    def set_active(self, product_id: str, active: bool) -> None: ...
    def last_alert_at(self, product_id: str, kind: str) -> Optional[datetime]: ...
    def add_alert(self, a: Alert) -> None: ...
    def alerts_since(self, user_id: Optional[str], since: datetime) -> list[Alert]: ...
    def pending_alerts(self, user_id: Optional[str]) -> list[Alert]: ...
    def mark_notified(self, ids: list[str]) -> None: ...
    def settings_for(self, user_id: Optional[str]) -> UserSettings: ...
    def push_subscriptions(self, user_id: Optional[str]) -> list[PushSubscription]: ...
    def add_push_subscription(self, s: PushSubscription) -> None: ...
    def remove_push_subscription(self, endpoint: str) -> None: ...


# ---------------------------------------------------------------- SQLite
SQLITE_SCHEMA = """
create table if not exists products (
  id text primary key, user_id text, title text not null, url text not null,
  site text not null, country text not null, external_id text, model_no text,
  image_url text, currency text not null, active integer not null default 1,
  variant text, fail_count integer not null default 0, last_error text, last_fetched_at text,
  verified integer not null default 0, risk_level text, risk_reasons text, category text,
  target_price real, tags text, purchased_at text, purchased_price real,
  created_at text not null,
  unique(url, variant)
);
create table if not exists price_snapshots (
  id integer primary key autoincrement, product_id text not null, price real not null,
  currency text not null, seller text, in_stock integer not null default 1, captured_at text not null,
  list_price real, suspect integer not null default 0
);
create index if not exists idx_snap on price_snapshots(product_id, captured_at);
create table if not exists alerts (
  id integer primary key autoincrement, product_id text not null, user_id text, kind text not null,
  price real not null, baseline real, pct real, read integer default 0, notified integer default 0,
  note text, created_at text not null
);
create table if not exists user_settings (
  user_id text primary key, threshold_pct real, window_days integer, notify_email integer,
  notify_telegram integer, notify_push integer default 1, email text, telegram_chat_id text, digest integer default 1, instant_target integer default 1
);
create table if not exists push_subscriptions (
  endpoint text primary key, user_id text, p256dh text not null, auth text not null, created_at text not null
);
"""


class SqliteStorage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SQLITE_SCHEMA)
        for col in ("digest", "instant_target"):   # 기존 DB 에 컬럼 추가 (v0.8)
            try:
                self.conn.execute(f"alter table user_settings add column {col} integer default 1")
                if col == "digest":   # v0.8 이전 알림은 이미 보낸 것 — 첫 다이제스트에 쏟아지지 않게
                    self.conn.execute("update alerts set notified=1 where notified=0")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass

    def list_products(self, active_only: bool = True) -> list[Product]:
        q = "select * from products" + (" where active=1" if active_only else "")
        return [self._row_to_product(r) for r in self.conn.execute(q)]

    def add_product(self, p: Product) -> Product:
        # unique(url, variant) 는 variant 가 NULL 이면 중복을 막지 못한다(SQLite 는 NULL 을 서로 다르게 봄) → 먼저 조회
        row = self.conn.execute("select * from products where url=? and variant is ?", (p.url, p.variant)).fetchone()
        if row:
            return self._row_to_product(row)
        p.id = p.id or str(uuid.uuid4())
        self.conn.execute(
            "insert or ignore into products(id,user_id,title,url,site,country,external_id,model_no,image_url,currency,active,variant,created_at)"
            " values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.user_id, p.title, p.url, p.site, p.country, p.external_id, p.model_no,
             p.image_url, p.currency, int(p.active), p.variant, _iso(datetime.now(timezone.utc))),
        )
        self.conn.commit()
        row = self.conn.execute("select * from products where url=? and variant is ?", (p.url, p.variant)).fetchone()
        return self._row_to_product(row)

    def update_product(self, p: Product) -> None:
        self.conn.execute(
            "update products set title=?, external_id=?, model_no=?, image_url=?, currency=? where id=?",
            (p.title, p.external_id, p.model_no, p.image_url, p.currency, p.id),
        )
        self.conn.commit()

    def mark_fetch(self, p: Product, error: Optional[str]) -> None:
        now = _iso(datetime.now(timezone.utc))
        if error:   # 실패도 '조회'다 — last_fetched_at 을 갱신해야 min_interval_hours 가 지켜져 차단된 사이트를 매시간 두드리지 않는다
            self.conn.execute("update products set fail_count=fail_count+1, last_error=?, last_fetched_at=? where id=?", (error[:300], now, p.id))
        else:
            self.conn.execute("update products set fail_count=0, last_error=null, last_fetched_at=? where id=?", (now, p.id))
        self.conn.commit()

    def update_risk(self, p: Product, level: str, reasons: str) -> None:
        self.conn.execute("update products set risk_level=?, risk_reasons=? where id=?", (level, reasons[:300], p.id))
        self.conn.commit()

    def latest_prices_by_model(self, model_no: str, currency: str, exclude_id: str) -> list[float]:
        rows = self.conn.execute(
            """select (select price from price_snapshots s where s.product_id=p.id and s.in_stock=1
                        order by captured_at desc limit 1) as price
               from products p where p.model_no=? and p.currency=? and p.id<>? and p.active=1""",
            (model_no, currency, exclude_id)).fetchall()
        return [r["price"] for r in rows if r["price"] is not None]

    def history(self, product_id: str, days: int) -> list[PriceSnapshot]:
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=days))
        rows = self.conn.execute(
            "select * from price_snapshots where product_id=? and captured_at>=? order by captured_at",
            (product_id, cutoff),
        )
        return [PriceSnapshot(r["product_id"], r["price"], r["currency"], r["seller"], bool(r["in_stock"]),
                              _parse(r["captured_at"]), r["list_price"], bool(r["suspect"])) for r in rows]

    def add_snapshot(self, s: PriceSnapshot) -> None:
        self.conn.execute(
            "insert into price_snapshots(product_id,price,currency,seller,in_stock,captured_at,list_price,suspect) values(?,?,?,?,?,?,?,?)",
            (s.product_id, s.price, s.currency, s.seller, int(s.in_stock), _iso(s.captured_at), s.list_price, int(s.suspect)),
        )
        self.conn.commit()

    def confirm_suspects(self, product_id: str, price: float) -> None:
        # 같은 수준(±5%)의 suspect 만 승격 — 예전 파싱 오류 값이 함께 '확정'되어 역대 최저를 오염시키지 않도록
        self.conn.execute("update price_snapshots set suspect=0 where product_id=? and suspect=1 and price between ? and ?",
                          (product_id, price * 0.95, price * 1.05))
        self.conn.commit()

    def set_active(self, product_id: str, active: bool) -> None:
        self.conn.execute("update products set active=? where id=?", (int(active), product_id))
        self.conn.commit()

    def last_alert_at(self, product_id: str, kind: str) -> Optional[datetime]:
        r = self.conn.execute(
            "select created_at from alerts where product_id=? and kind=? order by created_at desc limit 1",
            (product_id, kind),
        ).fetchone()
        return _parse(r["created_at"]) if r else None

    def add_alert(self, a: Alert) -> None:
        self.conn.execute(
            "insert into alerts(product_id,user_id,kind,price,baseline,pct,notified,note,created_at) values(?,?,?,?,?,?,?,?,?)",
            (a.product_id, a.user_id, a.kind, a.price, a.baseline, a.pct, int(a.notified), a.note, _iso(a.created_at)),
        )
        self.conn.commit()

    def alerts_since(self, user_id: Optional[str], since: datetime) -> list[Alert]:
        rows = self.conn.execute(
            "select * from alerts where user_id is ? and created_at>=? order by created_at desc", (user_id, _iso(since)))
        return [self._row_to_alert(r) for r in rows]

    def pending_alerts(self, user_id: Optional[str]) -> list[Alert]:
        rows = self.conn.execute("select * from alerts where user_id is ? and notified=0 order by created_at", (user_id,))
        return [self._row_to_alert(r) for r in rows]

    def mark_notified(self, ids: list[str]) -> None:
        if ids:
            self.conn.execute(f"update alerts set notified=1 where id in ({','.join('?' * len(ids))})", [int(i) for i in ids])
            self.conn.commit()

    def settings_for(self, user_id: Optional[str]) -> UserSettings:
        r = self.conn.execute("select * from user_settings where user_id=?", (user_id or "local",)).fetchone()
        if not r:
            return _default_settings(user_id)
        return UserSettings(r["user_id"], r["threshold_pct"], r["window_days"], bool(r["notify_email"]),
                            bool(r["notify_telegram"]), bool(r["notify_push"]), r["email"], r["telegram_chat_id"],
                            bool(r["digest"]) if r["digest"] is not None else True,
                            bool(r["instant_target"]) if r["instant_target"] is not None else True)

    def push_subscriptions(self, user_id: Optional[str]) -> list[PushSubscription]:
        rows = self.conn.execute("select * from push_subscriptions where user_id is ?", (user_id,))
        return [PushSubscription(r["endpoint"], r["p256dh"], r["auth"], r["user_id"]) for r in rows]

    def add_push_subscription(self, s: PushSubscription) -> None:
        self.conn.execute("insert or replace into push_subscriptions(endpoint,user_id,p256dh,auth,created_at) values(?,?,?,?,?)",
                          (s.endpoint, s.user_id, s.p256dh, s.auth, _iso(datetime.now(timezone.utc))))
        self.conn.commit()

    def remove_push_subscription(self, endpoint: str) -> None:
        self.conn.execute("delete from push_subscriptions where endpoint=?", (endpoint,))
        self.conn.commit()

    @staticmethod
    def _row_to_alert(r: sqlite3.Row) -> Alert:
        return Alert(r["product_id"], r["kind"], r["price"], r["baseline"], r["pct"], r["user_id"],
                     _parse(r["created_at"]), r["note"], str(r["id"]), bool(r["notified"]))

    @staticmethod
    def _row_to_product(r: sqlite3.Row) -> Product:
        return Product(r["id"], r["title"], r["url"], r["site"], r["country"], r["currency"],
                       r["external_id"], r["model_no"], r["image_url"], r["user_id"], bool(r["active"]),
                       r["variant"], r["fail_count"], r["last_error"], _parse(r["last_fetched_at"]),
                       bool(r["verified"]), r["risk_level"], r["risk_reasons"], r["category"],
                       r["target_price"], r["tags"], _parse(r["purchased_at"]), r["purchased_price"])


# ---------------------------------------------------------------- Supabase
class SupabaseStorage:
    def __init__(self, url: str, key: str):
        from supabase import create_client  # 지연 임포트: 개발 환경에선 불필요

        self.db = create_client(url, key)

    def list_products(self, active_only: bool = True) -> list[Product]:
        q = self.db.table("products").select("*")
        if active_only:
            q = q.eq("active", True)
        return [self._to_product(r) for r in q.execute().data]

    def add_product(self, p: Product) -> Product:
        # 있으면 그대로 반환 (DO UPDATE 로 제목·verified·active 를 덮어쓰지 않도록). user_id 가 없는 CLI 등록은 NULL 이 유니크에 안 걸리므로 반드시 먼저 조회.
        q = self.db.table("products").select("*").eq("url", p.url).eq("variant_key", p.variant or "")
        q = q.eq("user_id", p.user_id) if p.user_id else q.is_("user_id", "null")
        rows = q.limit(1).execute().data
        if rows:
            return self._to_product(rows[0])
        payload = {k: v for k, v in p.__dict__.items()
                   if k not in ("id", "fail_count", "last_error", "last_fetched_at", "risk_level", "risk_reasons",
                                "tags", "purchased_at", "purchased_price") and v is not None}
        r = self.db.table("products").upsert(payload, on_conflict="user_id,url,variant_key", ignore_duplicates=True).execute().data
        return self._to_product(r[0]) if r else self._to_product(q.limit(1).execute().data[0])

    def update_product(self, p: Product) -> None:
        self.db.table("products").update({
            "title": p.title, "external_id": p.external_id, "model_no": p.model_no,
            "image_url": p.image_url, "currency": p.currency,
        }).eq("id", p.id).execute()

    def mark_fetch(self, p: Product, error: Optional[str]) -> None:
        if error:
            self.db.table("products").update({"fail_count": p.fail_count + 1, "last_error": error[:300],
                                              "last_fetched_at": _iso(datetime.now(timezone.utc))}).eq("id", p.id).execute()
        else:
            self.db.table("products").update({"fail_count": 0, "last_error": None,
                                              "last_fetched_at": _iso(datetime.now(timezone.utc))}).eq("id", p.id).execute()

    def update_risk(self, p: Product, level: str, reasons: str) -> None:
        self.db.table("products").update({"risk_level": level, "risk_reasons": reasons[:300]}).eq("id", p.id).execute()

    def latest_prices_by_model(self, model_no: str, currency: str, exclude_id: str) -> list[float]:
        rows = (self.db.table("product_overview").select("last_price,last_in_stock").eq("model_no", model_no)
                .eq("currency", currency).eq("active", True).neq("id", exclude_id).execute().data)
        return [float(r["last_price"]) for r in rows if r.get("last_price") is not None and r.get("last_in_stock", True)]

    def history(self, product_id: str, days: int) -> list[PriceSnapshot]:
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=days))
        rows = (self.db.table("price_snapshots").select("*").eq("product_id", product_id)
                .gte("captured_at", cutoff).order("captured_at").execute().data)
        return [PriceSnapshot(r["product_id"], float(r["price"]), r["currency"], r.get("seller"),
                              bool(r["in_stock"]), _parse(r["captured_at"]),
                              float(r["list_price"]) if r.get("list_price") is not None else None,
                              bool(r.get("suspect", False))) for r in rows]

    def add_snapshot(self, s: PriceSnapshot) -> None:
        self.db.table("price_snapshots").insert({
            "product_id": s.product_id, "price": s.price, "currency": s.currency, "seller": s.seller,
            "in_stock": s.in_stock, "captured_at": _iso(s.captured_at), "list_price": s.list_price, "suspect": s.suspect,
        }).execute()

    def confirm_suspects(self, product_id: str, price: float) -> None:
        (self.db.table("price_snapshots").update({"suspect": False}).eq("product_id", product_id).eq("suspect", True)
         .gte("price", price * 0.95).lte("price", price * 1.05).execute())

    def set_active(self, product_id: str, active: bool) -> None:
        self.db.table("products").update({"active": active}).eq("id", product_id).execute()

    def last_alert_at(self, product_id: str, kind: str) -> Optional[datetime]:
        rows = (self.db.table("alerts").select("created_at").eq("product_id", product_id).eq("kind", kind)
                .order("created_at", desc=True).limit(1).execute().data)
        return _parse(rows[0]["created_at"]) if rows else None

    def add_alert(self, a: Alert) -> None:
        self.db.table("alerts").insert({
            "product_id": a.product_id, "user_id": a.user_id, "kind": a.kind, "price": a.price,
            "baseline": a.baseline, "pct": a.pct, "notified": a.notified, "note": a.note, "created_at": _iso(a.created_at),
        }).execute()

    def alerts_since(self, user_id: Optional[str], since: datetime) -> list[Alert]:
        q = self.db.table("alerts").select("*").gte("created_at", _iso(since)).order("created_at", desc=True)
        q = q.eq("user_id", user_id) if user_id else q.is_("user_id", "null")
        return [self._to_alert(r) for r in q.execute().data]

    def pending_alerts(self, user_id: Optional[str]) -> list[Alert]:
        q = self.db.table("alerts").select("*").eq("notified", False).order("created_at")
        q = q.eq("user_id", user_id) if user_id else q.is_("user_id", "null")
        return [self._to_alert(r) for r in q.execute().data]

    def mark_notified(self, ids: list[str]) -> None:
        if ids:
            self.db.table("alerts").update({"notified": True}).in_("id", [int(i) for i in ids]).execute()

    def settings_for(self, user_id: Optional[str]) -> UserSettings:
        rows = self.db.table("user_settings").select("*").eq("user_id", user_id).execute().data if user_id else []
        if not rows:
            return _default_settings(user_id)
        r = rows[0]
        return UserSettings(user_id, float(r["threshold_pct"]), int(r["window_days"]), r["notify_email"],
                            r["notify_telegram"], r.get("notify_push", True), r.get("email"), r.get("telegram_chat_id"),
                            bool(r.get("digest", True)), bool(r.get("instant_target", True)))

    def push_subscriptions(self, user_id: Optional[str]) -> list[PushSubscription]:
        if not user_id:
            return []
        rows = self.db.table("push_subscriptions").select("*").eq("user_id", user_id).execute().data
        return [PushSubscription(r["endpoint"], r["p256dh"], r["auth"], r["user_id"]) for r in rows]

    def add_push_subscription(self, s: PushSubscription) -> None:
        self.db.table("push_subscriptions").upsert({"endpoint": s.endpoint, "user_id": s.user_id,
                                                    "p256dh": s.p256dh, "auth": s.auth}, on_conflict="endpoint").execute()

    def remove_push_subscription(self, endpoint: str) -> None:
        self.db.table("push_subscriptions").delete().eq("endpoint", endpoint).execute()

    @staticmethod
    def _to_alert(r: dict) -> Alert:
        return Alert(r["product_id"], r["kind"], float(r["price"]),
                     float(r["baseline"]) if r.get("baseline") is not None else None,
                     float(r["pct"]) if r.get("pct") is not None else None,
                     r.get("user_id"), _parse(r["created_at"]), r.get("note"), str(r["id"]), bool(r.get("notified", True)))

    @staticmethod
    def _to_product(r: dict) -> Product:
        return Product(r["id"], r["title"], r["url"], r["site"], r["country"], r["currency"],
                       r.get("external_id"), r.get("model_no"), r.get("image_url"), r.get("user_id"), r["active"],
                       r.get("variant"), r.get("fail_count", 0), r.get("last_error"), _parse(r.get("last_fetched_at")),
                       bool(r.get("verified", False)), r.get("risk_level"), r.get("risk_reasons"), r.get("category"),
                       float(r["target_price"]) if r.get("target_price") is not None else None,
                       ",".join(r["tags"]) if isinstance(r.get("tags"), list) else r.get("tags"),
                       _parse(r.get("purchased_at")), float(r["purchased_price"]) if r.get("purchased_price") is not None else None)


def get_storage() -> Storage:
    if settings.use_supabase:
        return SupabaseStorage(settings.supabase_url, settings.supabase_key)
    return SqliteStorage(settings.sqlite_path)
