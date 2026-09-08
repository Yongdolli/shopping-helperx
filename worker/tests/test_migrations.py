"""supabase/ALL_MIGRATIONS.sql 을 실제 PostgreSQL 에서 검증 — Supabase 환경(auth.users, auth.uid(), extensions 스키마, anon/authenticated 롤)을 흉내 낸다.

실행 조건: 환경변수 PG_BIN 에 initdb/pg_ctl/postgres 가 있는 bin 폴더 + `pip install psycopg[binary]`. 없으면 skip.
  예) PG_BIN=C:\\pg\\bin pytest tests/test_migrations.py -q
검사: (1) 처음 실행 성공 (2) 재실행(멱등) 성공 (3) upsert on_conflict 키 (4) RLS + 공유 RPC (5) alerts kind 제약·설정 컬럼."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
PG_BIN = os.environ.get("PG_BIN", "")
ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "supabase" / "ALL_MIGRATIONS.sql"

pytestmark = pytest.mark.skipif(not PG_BIN or not (Path(PG_BIN) / ("initdb.exe" if os.name == "nt" else "initdb")).exists(),
                                reason="PG_BIN 미설정 — 임베디드 PostgreSQL 없음")

SUPABASE_STUB = """
create role anon nologin; create role authenticated nologin;
create schema extensions; create extension if not exists pgcrypto schema extensions;
create schema auth;
create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema public, extensions to anon, authenticated;
alter default privileges in schema public grant all on tables to anon, authenticated;
alter default privileges in schema public grant all on sequences to anon, authenticated;
alter default privileges in schema public grant execute on functions to anon, authenticated;
alter database postgres set search_path = public, extensions;
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    data = tmp_path_factory.mktemp("pgdata")
    exe = lambda n: str(Path(PG_BIN) / (n + (".exe" if os.name == "nt" else "")))  # noqa: E731
    subprocess.run([exe("initdb"), "-D", str(data), "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"], check=True, capture_output=True)
    port = _free_port()
    log = data / "pg.log"
    # capture_output 금지: 서버 프로세스가 파이프를 물고 있어 pg_ctl 이 끝나도 run() 이 영원히 기다린다 (Windows)
    subprocess.run([exe("pg_ctl"), "-D", str(data), "-o", f"-p {port} -c listen_addresses=127.0.0.1", "-l", str(log), "-w", "start"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    dsn = f"host=127.0.0.1 port={port} user=postgres dbname=postgres"
    try:
        for _ in range(50):
            try:
                psycopg.connect(dsn).close(); break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(SUPABASE_STUB)
        yield dsn
    finally:
        subprocess.run([exe("pg_ctl"), "-D", str(data), "-m", "immediate", "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(data, ignore_errors=True)


def _run_sql(dsn: str, sql: str) -> None:
    with psycopg.connect(dsn, autocommit=False) as c:
        c.execute(sql)
        c.commit()


def test_migrations_apply_and_are_idempotent(pg):
    sql = SQL.read_text(encoding="utf-8")
    _run_sql(pg, sql)            # 새 프로젝트
    _run_sql(pg, sql)            # 실패 후 재실행 / 두 번 붙여넣기
    with psycopg.connect(pg) as c:
        cols = {r[0] for r in c.execute("select column_name from information_schema.columns where table_name='products'")}
        assert {"variant", "variant_key", "target_price", "tags", "purchased_at", "risk_level", "category"} <= cols
        cols = {r[0] for r in c.execute("select column_name from information_schema.columns where table_name='user_settings'")}
        assert {"notify_push", "digest", "instant_target"} <= cols
        views = {r[0] for r in c.execute("select table_name from information_schema.views where table_schema='public'")}
        assert "product_overview" in views
        assert not [r for r in c.execute("select indexname from pg_indexes where indexname='products_user_url_variant'")]


def test_upsert_conflict_key_and_overview(pg):
    uid = uuid.uuid4()
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("insert into auth.users(id,email) values (%s,'a@b.c') on conflict do nothing", (uid,))
        for _ in range(2):   # 웹/워커의 upsert 와 동일한 충돌 키
            c.execute("""insert into products(user_id,url,title,site,country,currency,variant)
                         values (%s,'https://x.com/p/1','T','generic','US','USD',null)
                         on conflict (user_id,url,variant_key) do update set title=excluded.title""", (uid,))
        c.execute("""insert into products(user_id,url,title,site,country,currency,variant)
                     values (%s,'https://x.com/p/1','T','generic','US','USD','th=1')
                     on conflict (user_id,url,variant_key) do nothing""", (uid,))
        assert c.execute("select count(*) from products where user_id=%s", (uid,)).fetchone()[0] == 2
        pid = c.execute("select id from products where user_id=%s and variant is null", (uid,)).fetchone()[0]
        c.execute("insert into price_snapshots(product_id,price,currency,in_stock) values (%s,100,'USD',true)", (pid,))
        row = c.execute("select last_price, baseline_90d, last_suspect from product_overview where id=%s", (pid,)).fetchone()
        assert float(row[0]) == 100.0
        c.execute("insert into alerts(product_id,user_id,kind,price,notified) values (%s,%s,'target',90,false)", (pid, uid))
        c.execute("insert into alerts(product_id,user_id,kind,price) values (%s,%s,'paused',0)", (pid, uid))
        with pytest.raises(Exception):
            c.execute("insert into alerts(product_id,user_id,kind,price) values (%s,%s,'bogus',0)", (pid, uid))
        c.execute("insert into user_settings(user_id) values (%s) on conflict do nothing", (uid,))
        assert c.execute("select digest, instant_target from user_settings where user_id=%s", (uid,)).fetchone() == (True, True)


def test_rls_and_shared_rpc(pg):
    uid, other = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("insert into auth.users(id) values (%s),(%s)", (uid, other))
        c.execute("insert into products(user_id,url,title,site,country,currency,tags) values (%s,'https://x.com/p/s','공유','coupang','KR','KRW','{선물}')", (uid,))
        c.execute("insert into products(user_id,url,title,site,country,currency,tags) values (%s,'https://x.com/p/n','비공유','coupang','KR','KRW','{}')", (uid,))
        pid = c.execute("select id from products where url='https://x.com/p/s'").fetchone()[0]
        c.execute("insert into price_snapshots(product_id,price,currency) values (%s,50000,'KRW')", (pid,))
        c.execute("insert into shares(user_id,tag,name) values (%s,'선물','가족')", (uid,))
        token = c.execute("select token from shares where user_id=%s", (uid,)).fetchone()[0]
        assert len(token) == 24

    with psycopg.connect(pg, autocommit=True) as c:          # 익명 방문자
        c.execute("set role anon")
        assert c.execute("select count(*) from shares").fetchone()[0] == 0          # RLS: 테이블 직접 조회 불가
        assert c.execute("select count(*) from products").fetchone()[0] == 0
        assert c.execute("select name, tag from shared_info(%s)", (token,)).fetchone() == ("가족", "선물")
        titles = [r[0] for r in c.execute("select title from shared_products(%s)", (token,))]
        assert titles == ["공유"]                                                     # 태그 밖 상품은 안 보임
        assert c.execute("select count(*) from shared_snapshots(%s, 365)", (token,)).fetchone()[0] == 1
        assert c.execute("select count(*) from shared_products('nope')").fetchone()[0] == 0

    with psycopg.connect(pg, autocommit=True) as c:          # 다른 로그인 사용자
        c.execute("set role authenticated")
        c.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(other),))
        assert c.execute("select count(*) from products").fetchone()[0] == 0
        c.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(uid),))
        assert c.execute("select count(*) from products").fetchone()[0] == 2
        assert c.execute("select count(*) from shares").fetchone()[0] == 1
