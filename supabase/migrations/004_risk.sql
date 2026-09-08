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
