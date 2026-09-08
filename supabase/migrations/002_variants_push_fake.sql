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
