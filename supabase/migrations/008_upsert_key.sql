-- v0.8 버그 수정: 상품 upsert 충돌 키.
-- 002 의 `coalesce(variant, '')` 식(expression) 인덱스는 웹/워커가 쓰는 ON CONFLICT (user_id, url, variant) 와 매칭되지 않아
-- 상품 추가·북마클릿 기록·CSV 가져오기가 전부 42P10 오류로 실패했다. 생성 컬럼 variant_key 에 유니크 제약을 걸고 그 키로 upsert 한다.
alter table products add column if not exists variant_key text generated always as (coalesce(variant, '')) stored;
drop index if exists products_user_url_variant;
alter table products drop constraint if exists products_user_url_variant_key;
alter table products add constraint products_user_url_variant_key unique (user_id, url, variant_key);
