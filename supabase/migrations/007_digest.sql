-- v0.8: 하루 3회 다이제스트 (08:00·12:30·19:00 KST). true 면 워커가 알림을 저장만 하고(notified=false)
-- `python -m worker digest` 가 모아서 발송. false 면 감지 즉시 발송.
alter table user_settings add column if not exists digest boolean not null default true;
-- 목표가 도달(target)은 시간이 중요하므로 다이제스트를 건너뛰고 즉시 (기본 true)
alter table user_settings add column if not exists instant_target boolean not null default true;

-- v0.8 이전에 만들어진 알림은 이미 보낸 것 — 첫 다이제스트에 옛 알림이 쏟아지지 않게 백필
update alerts set notified = true where not notified;

create index if not exists idx_alerts_pending on alerts(user_id, notified) where not notified;
