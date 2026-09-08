-- v0.3: 북마클릿 수동 기록 — 사용자가 본인 상품의 스냅샷을 직접 넣을 수 있게
drop policy if exists "own snapshots insert" on price_snapshots;
create policy "own snapshots insert" on price_snapshots for insert
  with check (exists (select 1 from products p where p.id = product_id and p.user_id = auth.uid()));
