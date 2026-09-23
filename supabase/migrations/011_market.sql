-- v1.0: "평소보다 싼 딜" — 딜마다 다나와 전체 쇼핑몰 최저가를 관측해 쌓고(market_prices), 평소 가격(90일 중앙값) 대비 얼마나 싼지(below_pct).
alter table deals
  add column if not exists ref_price   numeric(14,2),               -- 평소 가격 (같은 상품 시세 관측 중앙값)
  add column if not exists ref_name    text,                        -- 매칭된 다나와 상품명
  add column if not exists ref_url     text,                        -- 다나와 상품 페이지
  add column if not exists below_pct   numeric(5,1),                -- (평소 가격 − 딜 가격)/평소 가격 %, 양수 = 평소보다 쌈
  add column if not exists ref_checked boolean not null default false;
create index if not exists idx_deals_below on deals(below_pct desc) where below_pct is not null;
create index if not exists idx_deals_price_todo on deals(posted_at desc) where not ref_checked;

create table if not exists market_prices (
  id          bigserial primary key,
  pcode       text not null,                -- 다나와 상품 코드
  name        text,
  price       numeric(14,2) not null,       -- 관측 시점 전체 쇼핑몰 최저가
  captured_at timestamptz not null default now()
);
create index if not exists idx_market_pcode_time on market_prices(pcode, captured_at desc);
alter table market_prices enable row level security;
drop policy if exists "market readable" on market_prices;
create policy "market readable" on market_prices for select to authenticated using (true);

-- "평소보다 N% 이상 싸면" 기본 10% (핵심 규칙과 동일). 기존에 30 으로 저장된 기본값도 10 으로.
alter table user_settings alter column deal_min_pct set default 10;
update user_settings set deal_min_pct = 10 where deal_min_pct = 30;
