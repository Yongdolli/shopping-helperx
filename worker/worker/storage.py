"""저장소: SQLite(개발) / Supabase(운영). 같은 인터페이스."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol

from .config import settings
import logging

from .models import Alert, Deal, PriceSnapshot, Product, PushSubscription, UserSettings

log = logging.getLogger(__name__)


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
                        settings.alert_email_to or None, settings.telegram_chat_id or None, settings.digest, True,
                        10.0, None)


class Storage(Protocol):
    def list_products(self, active_only: bool = True) -> list[Product]: ...
    def add_product(self, p: Product) -> Product: ...
    def update_product(self, p: Product) -> None: ...
    def mark_fetch(self, p: Product, error: Optional[str], count: bool = True) -> None: ...   # count=False: 실패로 세지 않음(자동 수집 불가)
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
    def upsert_deals(self, deals: list[Deal]) -> int: ...          # 새로 들어간 건수
    def list_deals(self, since: datetime) -> list[Deal]: ...
    def prune_deals(self, before: datetime) -> None: ...
    def deals_to_enrich(self, limit: int) -> list[Deal]: ...      # 보강 안 된 최신 딜
    def update_deal(self, d: Deal) -> None: ...                    # shop_url/list_price/pct/enriched/ref_* 반영
    def deals_to_price(self, limit: int) -> list[Deal]: ...       # 시세 확인 안 된 최근(3일) 가격 있는 딜
    def market_history(self, pcode: str, days: int) -> list[float]: ...
    def add_market_price(self, pcode: str, name: str, price: float) -> None: ...
    def sent_deal_keys(self, user_id: Optional[str], since: datetime) -> Optional[set[str]]: ...   # None = 기록 불가(012 전)
    def mark_deals_sent(self, user_id: Optional[str], keys: list[str]) -> None: ...
    def update_deal_stats(self, deals: list[Deal]) -> None: ...   # 이미 있는 딜의 추천·댓글·종료만 갱신 (종료는 한 번 되면 유지)
    def count_market_since(self, prefix: str, since: datetime) -> int: ...   # 예: 'coupang:' 최근 1시간 호출 수


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
create table if not exists deals (
  url text primary key, source text not null, site text not null, site_label text, title text not null,
  price real, currency text not null default 'KRW', shipping text, pct real, image_url text, category text,
  posted_at text not null, fetched_at text not null, shop_url text, list_price real, enriched integer not null default 0,
  ref_price real, ref_name text, ref_url text, below_pct real, ref_checked integer not null default 0,
  recommends integer, comments integer, ended integer not null default 0
);
create table if not exists deal_sends (
  user_key text not null, deal_key text not null, sent_at text not null, primary key (user_key, deal_key)
);
create table if not exists market_prices (
  id integer primary key autoincrement, pcode text not null, name text, price real not null, captured_at text not null
);
"""


class SqliteStorage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SQLITE_SCHEMA)
        for table, col, ddl in (("user_settings", "digest", "integer default 1"), ("user_settings", "instant_target", "integer default 1"),   # 기존 DB 에 컬럼 추가 (v0.8~)
                                ("user_settings", "deal_min_pct", "real default 10"), ("user_settings", "deal_keywords", "text"),
                                ("deals", "ref_price", "real"), ("deals", "ref_name", "text"), ("deals", "ref_url", "text"),
                                ("deals", "below_pct", "real"), ("deals", "ref_checked", "integer not null default 0"),
                                ("deals", "recommends", "integer"), ("deals", "comments", "integer"), ("deals", "ended", "integer not null default 0")):
            try:
                self.conn.execute(f"alter table {table} add column {col} {ddl}")
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

    def mark_fetch(self, p: Product, error: Optional[str], count: bool = True) -> None:
        now = _iso(datetime.now(timezone.utc))
        if error and not count:   # robots.txt 금지 등 영구 상태: 실패 카운트 0 으로 두고 사유만 기록
            self.conn.execute("update products set fail_count=0, last_error=?, last_fetched_at=? where id=?", (error[:300], now, p.id))
        elif error:   # 실패도 '조회'다 — last_fetched_at 을 갱신해야 min_interval_hours 가 지켜져 차단된 사이트를 매시간 두드리지 않는다
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
                            bool(r["instant_target"]) if r["instant_target"] is not None else True,
                            float(r["deal_min_pct"]) if r["deal_min_pct"] is not None else 10.0, r["deal_keywords"])

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

    def upsert_deals(self, deals: list[Deal]) -> int:
        n = 0
        for d in deals:
            cur = self.conn.execute(
                "insert or ignore into deals(url,source,site,site_label,title,price,currency,shipping,pct,image_url,category,posted_at,fetched_at,shop_url,list_price,enriched)"
                " values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (d.url, d.source, d.site, d.site_label, d.title, d.price, d.currency, d.shipping, d.pct, d.image_url, d.category,
                 _iso(d.posted_at), _iso(d.fetched_at), d.shop_url, d.list_price, int(d.enriched)))
            n += cur.rowcount
        self.conn.commit()
        return n

    def list_deals(self, since: datetime) -> list[Deal]:
        rows = self.conn.execute("select * from deals where posted_at>=? order by posted_at desc", (_iso(since),))
        return [self._row_to_deal(r) for r in rows]

    def prune_deals(self, before: datetime) -> None:
        self.conn.execute("delete from deals where posted_at<?", (_iso(before),))
        self.conn.commit()

    def deals_to_enrich(self, limit: int) -> list[Deal]:
        rows = self.conn.execute("select * from deals where enriched=0 order by posted_at desc limit ?", (limit,))
        return [self._row_to_deal(r) for r in rows]

    def update_deal(self, d: Deal) -> None:
        self.conn.execute("update deals set shop_url=?, list_price=?, pct=?, price=?, enriched=?, ref_price=?, ref_name=?, ref_url=?,"
                          " below_pct=?, ref_checked=? where url=?",
                          (d.shop_url, d.list_price, d.pct, d.price, int(d.enriched), d.ref_price, d.ref_name, d.ref_url,
                           d.below_pct, int(d.ref_checked), d.url))
        self.conn.commit()

    def deals_to_price(self, limit: int) -> list[Deal]:
        since = _iso(datetime.now(timezone.utc) - timedelta(days=3))
        rows = self.conn.execute("select * from deals where ref_checked=0 and price is not null and posted_at>=? order by posted_at desc limit ?",
                                 (since, limit))
        return [self._row_to_deal(r) for r in rows]

    def market_history(self, pcode: str, days: int) -> list[float]:
        since = _iso(datetime.now(timezone.utc) - timedelta(days=days))
        return [r["price"] for r in self.conn.execute("select price from market_prices where pcode=? and captured_at>=?", (pcode, since))]

    def add_market_price(self, pcode: str, name: str, price: float) -> None:
        self.conn.execute("insert into market_prices(pcode,name,price,captured_at) values(?,?,?,?)",
                          (pcode, name, price, _iso(datetime.now(timezone.utc))))
        self.conn.commit()

    def sent_deal_keys(self, user_id: Optional[str], since: datetime) -> Optional[set[str]]:
        rows = self.conn.execute("select deal_key from deal_sends where user_key=? and sent_at>=?", (user_id or "local", _iso(since)))
        return {r["deal_key"] for r in rows}

    def update_deal_stats(self, deals: list[Deal]) -> None:
        for d in deals:
            self.conn.execute("update deals set recommends=coalesce(?,recommends), comments=coalesce(?,comments), ended=max(ended,?) where url=?",
                              (d.recommends, d.comments, int(d.ended), d.url))
        self.conn.commit()

    def count_market_since(self, prefix: str, since: datetime) -> int:
        return self.conn.execute("select count(*) from market_prices where pcode like ? and captured_at>=?", (prefix + "%", _iso(since))).fetchone()[0]

    def mark_deals_sent(self, user_id: Optional[str], keys: list[str]) -> None:
        now = _iso(datetime.now(timezone.utc))
        self.conn.executemany("insert or replace into deal_sends(user_key,deal_key,sent_at) values(?,?,?)", [(user_id or "local", k, now) for k in keys])
        self.conn.commit()

    @staticmethod
    def _row_to_deal(r: sqlite3.Row) -> Deal:
        return Deal(r["url"], r["source"], r["site"], r["site_label"] or "", r["title"], r["price"], r["currency"], r["shipping"],
                    r["pct"], _parse(r["posted_at"]), _parse(r["fetched_at"]), r["image_url"], r["category"],
                    r["shop_url"], r["list_price"], bool(r["enriched"]), r["ref_price"], r["ref_name"], r["ref_url"],
                    r["below_pct"], bool(r["ref_checked"]), r["recommends"], r["comments"], bool(r["ended"]))

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

    def mark_fetch(self, p: Product, error: Optional[str], count: bool = True) -> None:
        if error:
            self.db.table("products").update({"fail_count": p.fail_count + 1 if count else 0, "last_error": error[:300],
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
                            bool(r.get("digest", True)), bool(r.get("instant_target", True)),
                            float(r.get("deal_min_pct") or 10), ",".join(r.get("deal_keywords") or []) or None)

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

    def upsert_deals(self, deals: list[Deal]) -> int:
        if not deals:
            return 0
        rows = [{"url": d.url, "source": d.source, "site": d.site, "site_label": d.site_label, "title": d.title, "price": d.price,
                 "currency": d.currency, "shipping": d.shipping, "pct": d.pct, "image_url": d.image_url, "category": d.category,
                 "posted_at": _iso(d.posted_at), "fetched_at": _iso(d.fetched_at), "shop_url": d.shop_url, "list_price": d.list_price,
                 "enriched": d.enriched} for d in deals]
        n = 0
        for i in range(0, len(rows), 100):
            n += len(self.db.table("deals").upsert(rows[i:i + 100], on_conflict="url", ignore_duplicates=True).execute().data)
        return n

    def list_deals(self, since: datetime) -> list[Deal]:
        rows = self.db.table("deals").select("*").gte("posted_at", _iso(since)).order("posted_at", desc=True).limit(1000).execute().data
        return [self._to_deal(r) for r in rows]

    def prune_deals(self, before: datetime) -> None:
        self.db.table("deals").delete().lt("posted_at", _iso(before)).execute()

    def deals_to_enrich(self, limit: int) -> list[Deal]:
        rows = self.db.table("deals").select("*").eq("enriched", False).order("posted_at", desc=True).limit(limit).execute().data
        return [self._to_deal(r) for r in rows]

    def update_deal(self, d: Deal) -> None:
        base = {"shop_url": d.shop_url, "list_price": d.list_price, "pct": d.pct, "price": d.price, "enriched": d.enriched}
        full = {**base, "ref_price": d.ref_price, "ref_name": d.ref_name, "ref_url": d.ref_url, "below_pct": d.below_pct,
                "ref_checked": d.ref_checked}
        try:
            self.db.table("deals").update(full).eq("url", d.url).execute()
        except Exception as e:  # noqa: BLE001 — 011 마이그레이션 전이면 시세 컬럼 없이 저장
            if "ref_" not in str(e) and "below_pct" not in str(e) and "PGRST204" not in str(e):
                raise
            self.db.table("deals").update(base).eq("url", d.url).execute()

    def deals_to_price(self, limit: int) -> list[Deal]:
        since = _iso(datetime.now(timezone.utc) - timedelta(days=3))
        try:
            rows = (self.db.table("deals").select("*").eq("ref_checked", False).not_.is_("price", "null").gte("posted_at", since)
                    .order("posted_at", desc=True).limit(limit).execute().data)
        except Exception as e:  # noqa: BLE001
            log.warning("시세 확인 건너뜀 (011_market.sql 실행 필요): %s", str(e)[:100])
            return []
        return [self._to_deal(r) for r in rows]

    def market_history(self, pcode: str, days: int) -> list[float]:
        since = _iso(datetime.now(timezone.utc) - timedelta(days=days))
        rows = self.db.table("market_prices").select("price").eq("pcode", pcode).gte("captured_at", since).execute().data
        return [float(r["price"]) for r in rows]

    def add_market_price(self, pcode: str, name: str, price: float) -> None:
        self.db.table("market_prices").insert({"pcode": pcode, "name": name, "price": price}).execute()

    def sent_deal_keys(self, user_id: Optional[str], since: datetime) -> Optional[set[str]]:
        try:
            rows = (self.db.table("deal_sends").select("deal_key").eq("user_key", user_id or "local")
                    .gte("sent_at", _iso(since)).limit(5000).execute().data)
        except Exception as e:  # noqa: BLE001 — 012 마이그레이션 전
            log.warning("보낸 딜 기록 없음 (012_deal_sends.sql 실행 필요): %s", str(e)[:80])
            return None
        return {r["deal_key"] for r in rows}

    def update_deal_stats(self, deals: list[Deal]) -> None:
        """바뀐 것만 PATCH. 013 전이면 조용히 건너뜀."""
        by = {d.url: d for d in deals}
        urls = list(by)
        for i in range(0, len(urls), 80):
            try:
                cur = self.db.table("deals").select("url,recommends,comments,ended").in_("url", urls[i:i + 80]).execute().data
            except Exception as e:  # noqa: BLE001
                log.warning("딜 통계 건너뜀 (013_deal_stats.sql 실행 필요): %s", str(e)[:80])
                return
            for r in cur:
                d = by[r["url"]]
                new = {"recommends": d.recommends if d.recommends is not None else r.get("recommends"),
                       "comments": d.comments if d.comments is not None else r.get("comments"),
                       "ended": bool(r.get("ended")) or d.ended}
                if new != {"recommends": r.get("recommends"), "comments": r.get("comments"), "ended": bool(r.get("ended"))}:
                    self.db.table("deals").update(new).eq("url", r["url"]).execute()

    def count_market_since(self, prefix: str, since: datetime) -> int:
        r = self.db.table("market_prices").select("id", count="exact", head=True).like("pcode", prefix + "%").gte("captured_at", _iso(since)).execute()
        return r.count or 0

    def mark_deals_sent(self, user_id: Optional[str], keys: list[str]) -> None:
        if not keys:
            return
        try:
            self.db.table("deal_sends").upsert([{"user_key": user_id or "local", "deal_key": k} for k in keys],
                                               on_conflict="user_key,deal_key").execute()
        except Exception as e:  # noqa: BLE001
            log.warning("보낸 딜 기록 실패: %s", str(e)[:80])

    @staticmethod
    def _to_deal(r: dict) -> Deal:
        f = lambda k: float(r[k]) if r.get(k) is not None else None  # noqa: E731
        return Deal(r["url"], r["source"], r["site"], r.get("site_label") or "", r["title"], f("price"), r.get("currency") or "KRW",
                    r.get("shipping"), f("pct"), _parse(r["posted_at"]), _parse(r.get("fetched_at")) or _parse(r["posted_at"]),
                    r.get("image_url"), r.get("category"), r.get("shop_url"), f("list_price"), bool(r.get("enriched", False)),
                    f("ref_price"), r.get("ref_name"), r.get("ref_url"), f("below_pct"), bool(r.get("ref_checked", False)),
                    r.get("recommends"), r.get("comments"), bool(r.get("ended", False)))

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
