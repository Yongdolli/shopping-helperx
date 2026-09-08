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
