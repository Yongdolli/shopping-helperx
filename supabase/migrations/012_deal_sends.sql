-- v1.0 수정: 다이제스트가 같은 딜을 두 번 보내거나(창 겹침) 저녁 딜을 빠뜨리지(창 구멍) 않도록, 보낸 딜을 기록한다.
-- 다이제스트는 최근 24시간 딜 중 아직 안 보낸 것만 고른다(늦게 시세가 확인된 딜도 다음 슬롯에 포함). 워커만 읽고 쓴다(service key).
create table if not exists deal_sends (
  user_key  text not null,                 -- user_id (로컬 SQLite 는 'local')
  deal_key  text not null,                 -- deals.same_key: 제목 글자 + 가격 (여러 커뮤니티의 같은 딜 = 같은 키)
  sent_at   timestamptz not null default now(),
  primary key (user_key, deal_key)
);
alter table deal_sends enable row level security;   -- 정책 없음 = 웹(anon/authenticated) 접근 불가
