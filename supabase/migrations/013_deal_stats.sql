-- v1.1: 끝난 딜 숨기기 + 인기 딜. 워커가 매 실행마다 커뮤니티 목록에서 추천·댓글 수와 종료/품절 표시를 갱신한다.
alter table deals
  add column if not exists recommends int,                         -- 커뮤니티 추천 수 (뽐뿌 RSS · 루리웹 목록 · 클리앙 ♥)
  add column if not exists comments   int,                         -- 댓글 수
  add column if not exists ended      boolean not null default false; -- 종료·품절 (루리웹 [종료], 클리앙 품절, 제목의 종료/품절/마감)
create index if not exists idx_deals_active on deals(posted_at desc) where not ended;
