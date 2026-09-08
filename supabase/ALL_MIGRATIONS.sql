-- Shopping Helper 전체 마이그레이션 (001~010) — 새 프로젝트에 한 번에 붙여넣기용. 개별 파일과 내용 동일.
-- 재실행해도 안전(멱등): 어느 단계에서 실패했든 전체를 다시 Run 하면 된다.

-- ==================== 001_init.sql ====================
-- Shopping Helper 초기 스키마
create extension if not exists "pgcrypto";

create table if not exists products (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references auth.users(id) on delete cascade,
  title       text not null,
  url         text not null,
  site        text not null,              -- coupang, 11st, aliexpress, amazon, ebay, bestbuy, walmart, ...
  country     text not null default 'KR', -- KR, CN, US
  external_id text,                       -- ASIN, itemId 등 플랫폼 ID
  model_no    text,                       -- 동일 품목 매칭 키
  image_url   text,
  currency    text not null default 'KRW',
  active      boolean not null default true,
  created_at  timestamptz not null default now(),
  unique (user_id, url)
);

create table if not exists price_snapshots (
  id          bigserial primary key,
  product_id  uuid not null references products(id) on delete cascade,
  price       numeric(14,2) not null,
  currency    text not null,
  seller      text,
  in_stock    boolean not null default true,
  captured_at timestamptz not null default now()
);
create index if not exists idx_snapshots_product_time on price_snapshots(product_id, captured_at desc);

create table if not exists alerts (
  id          bigserial primary key,
  product_id  uuid not null references products(id) on delete cascade,
  user_id     uuid references auth.users(id) on delete cascade,
  kind        text not null check (kind in ('drop','low','restock')),
  price       numeric(14,2) not null,
  baseline    numeric(14,2),
  pct         numeric(6,2),               -- 기준선 대비 하락률(양수)
  read        boolean not null default false,
  notified    boolean not null default false,
  created_at  timestamptz not null default now()
);
create index if not exists idx_alerts_user_time on alerts(user_id, created_at desc);

create table if not exists user_settings (
  user_id          uuid primary key references auth.users(id) on delete cascade,
  threshold_pct    numeric(5,2) not null default 10,
  window_days      int not null default 90,
  notify_email     boolean not null default false,
  notify_telegram  boolean not null default false,
  email            text,
  telegram_chat_id text,
  updated_at       timestamptz not null default now()
);

-- RLS: 본인 데이터만
alter table products enable row level security;
alter table price_snapshots enable row level security;
alter table alerts enable row level security;
alter table user_settings enable row level security;

drop policy if exists "own products" on products;
create policy "own products" on products for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "own snapshots" on price_snapshots;
create policy "own snapshots" on price_snapshots for select
  using (exists (select 1 from products p where p.id = product_id and p.user_id = auth.uid()));
drop policy if exists "own alerts" on alerts;
create policy "own alerts" on alerts for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "own settings" on user_settings;
create policy "own settings" on user_settings for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- 워커는 service key 로 접근하므로 RLS 우회.

-- 최신가·기준선 뷰 (웹 대시보드용)
drop view if exists product_overview;
create view product_overview as
select
  p.*,
  ls.price      as last_price,
  ls.captured_at as last_captured_at,
  (select percentile_cont(0.5) within group (order by s.price)
     from price_snapshots s
    where s.product_id = p.id and s.captured_at > now() - interval '90 days') as baseline_90d,
  (select min(s.price) from price_snapshots s where s.product_id = p.id) as all_time_low
from products p
left join lateral (
  select price, captured_at from price_snapshots s
  where s.product_id = p.id order by captured_at desc limit 1
) ls on true;

-- ==================== 002_variants_push_fake.sql ====================
-- v0.2: 옵션(variant) 분리, 웹푸시 구독, 정가(list_price) 수집, 실패 카운트, 알림 메모

alter table products
  add column if not exists variant text,
  add column if not exists fail_count int not null default 0,
  add column if not exists last_error text,
  add column if not exists last_fetched_at timestamptz;

-- (user_id, url) 유니크 → (user_id, url, variant)
alter table products drop constraint if exists products_user_id_url_key;
create unique index if not exists products_user_url_variant on products(user_id, url, coalesce(variant, ''));

alter table price_snapshots add column if not exists list_price numeric(14,2);

alter table alerts drop constraint if exists alerts_kind_check;
alter table alerts add constraint alerts_kind_check check (kind in ('drop','low','restock','fake'));
alter table alerts add column if not exists note text;

alter table user_settings add column if not exists notify_push boolean not null default true;

create table if not exists push_subscriptions (
  endpoint   text primary key,
  user_id    uuid not null references auth.users(id) on delete cascade,
  p256dh     text not null,
  auth       text not null,
  created_at timestamptz not null default now()
);
alter table push_subscriptions enable row level security;
drop policy if exists "own push subs" on push_subscriptions;
create policy "own push subs" on push_subscriptions for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- 뷰 갱신: 최신 정가·판매자 포함
drop view if exists product_overview;
create view product_overview as
select
  p.*,
  ls.price        as last_price,
  ls.list_price   as last_list_price,
  ls.seller       as last_seller,
  ls.in_stock     as last_in_stock,
  ls.captured_at  as last_captured_at,
  (select percentile_cont(0.5) within group (order by s.price)
     from price_snapshots s
    where s.product_id = p.id and s.in_stock and s.captured_at > now() - interval '90 days') as baseline_90d,
  (select min(s.price) from price_snapshots s where s.product_id = p.id and s.in_stock) as all_time_low
from products p
left join lateral (
  select price, list_price, seller, in_stock, captured_at from price_snapshots s
  where s.product_id = p.id order by captured_at desc limit 1
) ls on true;

-- ==================== 003_capture.sql ====================
-- v0.3: 북마클릿 수동 기록 — 사용자가 본인 상품의 스냅샷을 직접 넣을 수 있게
drop policy if exists "own snapshots insert" on price_snapshots;
create policy "own snapshots insert" on price_snapshots for insert
  with check (exists (select 1 from products p where p.id = product_id and p.user_id = auth.uid()));

-- ==================== 004_risk.sql ====================
-- v0.4: 정품 리스크 점수 + 사용자 '정품 확인됨' 표시
alter table products
  add column if not exists verified boolean not null default false,
  add column if not exists risk_level text check (risk_level in ('low','medium','high')),
  add column if not exists risk_reasons text;

-- 뷰 재생성 (컬럼 추가 반영)
drop view if exists product_overview;
create view product_overview as
select
  p.*,
  ls.price        as last_price,
  ls.list_price   as last_list_price,
  ls.seller       as last_seller,
  ls.in_stock     as last_in_stock,
  ls.captured_at  as last_captured_at,
  (select percentile_cont(0.5) within group (order by s.price)
     from price_snapshots s
    where s.product_id = p.id and s.in_stock and s.captured_at > now() - interval '90 days') as baseline_90d,
  (select min(s.price) from price_snapshots s where s.product_id = p.id and s.in_stock) as all_time_low
from products p
left join lateral (
  select price, list_price, seller, in_stock, captured_at from price_snapshots s
  where s.product_id = p.id order by captured_at desc limit 1
) ls on true;

-- ==================== 005_confirm_landed.sql ====================
-- v0.5: 극단값 확인(suspect), 자동 중단 알림(paused), 관세 카테고리
alter table price_snapshots add column if not exists suspect boolean not null default false;
alter table products add column if not exists category text;

alter table alerts drop constraint if exists alerts_kind_check;
alter table alerts add constraint alerts_kind_check check (kind in ('drop','low','restock','fake','paused'));

-- 뷰 재생성: suspect 제외한 기준선·최저가
drop view if exists product_overview;
create view product_overview as
select
  p.*,
  ls.price        as last_price,
  ls.list_price   as last_list_price,
  ls.seller       as last_seller,
  ls.in_stock     as last_in_stock,
  ls.suspect      as last_suspect,
  ls.captured_at  as last_captured_at,
  (select percentile_cont(0.5) within group (order by s.price)
     from price_snapshots s
    where s.product_id = p.id and s.in_stock and not s.suspect and s.captured_at > now() - interval '90 days') as baseline_90d,
  (select min(s.price) from price_snapshots s where s.product_id = p.id and s.in_stock and not s.suspect) as all_time_low
from products p
left join lateral (
  select price, list_price, seller, in_stock, suspect, captured_at from price_snapshots s
  where s.product_id = p.id order by captured_at desc limit 1
) ls on true;

-- ==================== 006_target_purchase_tags.sql ====================
-- v0.6: 목표가, 구매 기록(절약액), 태그, 목표가 알림 종류
alter table products
  add column if not exists target_price numeric(14,2),
  add column if not exists tags text[] not null default '{}',
  add column if not exists purchased_at timestamptz,
  add column if not exists purchased_price numeric(14,2);

alter table alerts drop constraint if exists alerts_kind_check;
alter table alerts add constraint alerts_kind_check check (kind in ('target','drop','low','restock','fake','paused'));

drop view if exists product_overview;
create view product_overview as
select
  p.*,
  ls.price        as last_price,
  ls.list_price   as last_list_price,
  ls.seller       as last_seller,
  ls.in_stock     as last_in_stock,
  ls.suspect      as last_suspect,
  ls.captured_at  as last_captured_at,
  (select percentile_cont(0.5) within group (order by s.price)
     from price_snapshots s
    where s.product_id = p.id and s.in_stock and not s.suspect and s.captured_at > now() - interval '90 days') as baseline_90d,
  (select min(s.price) from price_snapshots s where s.product_id = p.id and s.in_stock and not s.suspect) as all_time_low
from products p
left join lateral (
  select price, list_price, seller, in_stock, suspect, captured_at from price_snapshots s
  where s.product_id = p.id order by captured_at desc limit 1
) ls on true;

-- ==================== 007_digest.sql ====================
-- v0.8: 하루 3회 다이제스트 (08:00·12:30·19:00 KST). true 면 워커가 알림을 저장만 하고(notified=false)
-- `python -m worker digest` 가 모아서 발송. false 면 감지 즉시 발송.
alter table user_settings add column if not exists digest boolean not null default true;
-- 목표가 도달(target)은 시간이 중요하므로 다이제스트를 건너뛰고 즉시 (기본 true)
alter table user_settings add column if not exists instant_target boolean not null default true;

-- v0.8 이전에 만들어진 알림은 이미 보낸 것 — 첫 다이제스트에 옛 알림이 쏟아지지 않게 백필
update alerts set notified = true where not notified;

create index if not exists idx_alerts_pending on alerts(user_id, notified) where not notified;

-- ==================== 008_upsert_key.sql ====================
-- v0.8 버그 수정: 상품 upsert 충돌 키.
-- 002 의 `coalesce(variant, '')` 식(expression) 인덱스는 웹/워커가 쓰는 ON CONFLICT (user_id, url, variant) 와 매칭되지 않아
-- 상품 추가·북마클릿 기록·CSV 가져오기가 전부 42P10 오류로 실패했다. 생성 컬럼 variant_key 에 유니크 제약을 걸고 그 키로 upsert 한다.
alter table products add column if not exists variant_key text generated always as (coalesce(variant, '')) stored;
drop index if exists products_user_url_variant;
alter table products drop constraint if exists products_user_url_variant_key;
alter table products add constraint products_user_url_variant_key unique (user_id, url, variant_key);

-- ==================== 009_shares.sql ====================
-- v0.8: 가족 공유 — 태그(또는 전체) 단위 읽기 전용 공유 링크. 링크를 가진 사람은 로그인 없이(anon) 조회.
-- 소유자만 링크를 만들고 지운다(RLS). 열람은 security definer 함수로만 — 토큰이 곧 권한이므로 토큰은 추측 불가(12바이트 난수).
create table if not exists shares (
  token       text primary key default encode(gen_random_bytes(12), 'hex'),
  user_id     uuid not null references auth.users(id) on delete cascade,
  tag         text,                       -- null = 전체 활성 상품
  name        text not null default '가족',
  created_at  timestamptz not null default now()
);
alter table shares enable row level security;
drop policy if exists "own shares" on shares;
create policy "own shares" on shares for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create or replace function shared_info(p_token text)
returns table(token text, name text, tag text, created_at timestamptz)
language sql security definer stable as $$
  select s.token, s.name, s.tag, s.created_at from shares s where s.token = p_token
$$;

create or replace function shared_products(p_token text)
returns setof products
language sql security definer stable as $$
  select p.* from products p join shares s on s.user_id = p.user_id
  where s.token = p_token and p.active and (s.tag is null or s.tag = any(p.tags))
  order by p.created_at desc
$$;

create or replace function shared_snapshots(p_token text, p_days int default 365)
returns table(product_id uuid, price numeric, list_price numeric, currency text, seller text, in_stock boolean, suspect boolean, captured_at timestamptz)
language sql security definer stable as $$
  select ps.product_id, ps.price, ps.list_price, ps.currency, ps.seller, ps.in_stock, ps.suspect, ps.captured_at
  from price_snapshots ps
  join products p on p.id = ps.product_id
  join shares s on s.user_id = p.user_id
  where s.token = p_token and p.active and (s.tag is null or s.tag = any(p.tags))
    and ps.captured_at > now() - make_interval(days => p_days)
  order by ps.captured_at
$$;

revoke all on function shared_info(text) from public;
revoke all on function shared_products(text) from public;
revoke all on function shared_snapshots(text, int) from public;
grant execute on function shared_info(text) to anon, authenticated;
grant execute on function shared_products(text) to anon, authenticated;
grant execute on function shared_snapshots(text, int) to anon, authenticated;

-- ==================== 010_deals.sql ====================
-- v0.9: 딜 피드 — 등록하지 않은 상품까지 핫딜 커뮤니티(뽐뿌·루리웹·클리앙·퀘이사존·에펨코리아)에서 모아 본다.
-- 전 사용자 공용 테이블: 워커(service key)가 쓰고, 로그인 사용자는 읽기만.
create table if not exists deals (
  id          bigserial primary key,
  url         text not null unique,          -- 게시글 URL (중복 제거 키)
  source      text not null,                 -- ppomppu | ruliweb | clien | quasarzone | fmkorea
  site        text not null,                 -- 우리 site 키 (coupang, gmarket …) 또는 상점명 소문자
  site_label  text,                          -- 원문 [사이트]
  title       text not null,
  price       numeric(14,2),
  currency    text not null default 'KRW',
  shipping    text,
  pct         numeric(5,1),                  -- 제목에 명시된 할인율만 (없으면 null)
  image_url   text,
  category    text,
  shop_url    text,                          -- 게시글에서 찾은 상점 상품 주소 (있으면 원클릭 추적)
  list_price  numeric(14,2),                 -- 상점 페이지에서 읽은 정가 (있으면 pct 계산 근거)
  enriched    boolean not null default false, -- 게시글·상점 페이지 보강 시도 완료
  posted_at   timestamptz not null,
  fetched_at  timestamptz not null default now()
);
create index if not exists idx_deals_posted on deals(posted_at desc);
create index if not exists idx_deals_pct on deals(pct desc) where pct is not null;
create index if not exists idx_deals_enrich on deals(posted_at desc) where not enriched;
alter table deals enable row level security;
drop policy if exists "deals readable" on deals;
create policy "deals readable" on deals for select to authenticated using (true);

-- 사용자별 딜 필터: 최소 할인율(기본 30%), 관심 키워드
alter table user_settings
  add column if not exists deal_min_pct numeric(5,1) not null default 30,
  add column if not exists deal_keywords text[] not null default '{}';
