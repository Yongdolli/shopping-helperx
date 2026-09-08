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
