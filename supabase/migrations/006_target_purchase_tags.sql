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
