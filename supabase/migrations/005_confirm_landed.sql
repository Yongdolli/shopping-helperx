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
