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
