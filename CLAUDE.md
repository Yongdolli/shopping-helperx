# Shopping Helper — Claude Code 프로젝트 가이드

한국·중국·미국 쇼핑몰 가격을 주기적으로 수집해, 같은 상품이 **최근 90일 중앙값 대비 10% 이상 싸지면** 알려주는 서비스.
폰·패드·PC 공용 PWA + Python 수집 워커 + Supabase. 현재 v0.8.

## 구조

```
web/        React + Vite + TS + Tailwind v4 + Zustand PWA (사용자 화면, src/sw.ts 서비스워커 = 웹푸시 수신)
worker/     Python 수집 워커: 어댑터 → 스냅샷 저장 → 기준선 계산 → 알림 판정 → 발송(푸시·텔레그램·이메일) + 주간 리포트(report.py)
supabase/   DB 마이그레이션 SQL (001 초기, 002 옵션·푸시·정가, 003 수동 기록 RLS, 004 정품 리스크, 005 극단값 확인·관세 카테고리, 006 목표가·구매·태그, 007 다이제스트·목표가 즉시, 008 upsert 키 수정, 009 가족 공유)
extension/  Chrome 확장(MV3) — 북마클릿과 같은 추출 로직을 build.mjs 가 content.js 로 생성. 원클릭 가격 기록
github-workflows/  GitHub Actions 크론: collect.yml(매시) · daily-digest.yml(08:00·12:30·19:00 KST) · weekly-report.yml(월요일 09:00 KST). push-to-github.cmd 가 .github/workflows/ 로 옮김
docs/       구상안·설계 문서
```

## 핵심 규칙 (바꾸려면 문서 먼저 갱신)

- 기준선 = 최근 `window_days`(기본 90일) 스냅샷의 **중앙값**. 평균 금지(가짜 할인에 취약). 3개 미만이면 기준선 없음. `suspect` 스냅샷은 제외.
- **극단값 2회 확인** (`baseline.needs_confirmation`, CONFIRM_PCT=40): 기준선 대비 -40% 이상이면 첫 수집은 `suspect=True` 로 기록만(알림 X, 기준선 제외).
  다음 수집이 같은 수준(±5%)이면 `confirm_suspects(product_id, price)` 로 **그 수준의 suspect 만** 승격 후 정상 판정(`baseline.confirms_suspect`). 정상가로 돌아오면 승격하지 않고 suspect 로 남긴다(역대 최저·기준선 오염 방지).
  파싱 오류로 1/10 가격이 읽혀도 오탐 알림이 나가지 않게 하는 장치. 북마클릿 기록은 사용자가 봤으므로 제외.
- **자동 중단**: 연속 실패 `PAUSE_AFTER_FAILS=10` 회면 `active=False` + `kind=paused` 알림. 상세에서 재개 가능.
- 알림 종류 우선순위: `target`(목표가 이하) > `drop`(기준선 대비 -threshold 이상) > `low`(역대 최저 갱신) > `restock` > `fake`(가짜 할인) (+ `paused` 자동 중단).
  같은 상품·종류는 24시간에 1회, `fake` 는 7일에 1회.
- **다이제스트** (`user_settings.digest`, 기본 true, `worker/digest.py`): 워커는 알림을 `notified=False` 로 저장만 하고 `python -m worker digest` 가 아침 08:00·점심 12:30·저녁 19:00 KST 에
  대기 알림을 사용자별로 모아 한 번에 발송(종류 우선순위 순, 같은 상품·종류는 최신 1건). 새 알림이 없으면 발송 없음. digest=false 면 감지 즉시 발송(기존 동작). 앱 알림 탭에는 항상 즉시 쌓임.
  SQLite 로컬 사용자 기본값은 env `DIGEST`(기본 1). `instant_target`(기본 true)이면 `target` 은 다이제스트를 건너뛰고 즉시.
- **가족 공유** (`shares` 테이블, 009): 태그(또는 전체) 단위 읽기 전용 링크 `/s/<token>`. 로그인 없이 열리며 `shared_info/shared_products/shared_snapshots` security definer RPC 로만 읽는다
  (anon 은 테이블 직접 접근 불가, 토큰 12바이트 난수). 웹은 받은 상품·스냅샷으로 `overview/enrich` 를 그대로 돌려 카드를 만든다(임계값 10%, 90일). 구매 완료·비활성 상품 제외. 데모 모드는 같은 브라우저에서만.
- **가짜 할인** = 사이트 표시 할인율(정가 대비) ≥ 20% 인데 실제(기준선 대비) ≤ 3%. `baseline.is_fake_discount`.
- **옵션 분리** = URL 의 옵션 파라미터(`models.VARIANT_PARAMS`: 쿠팡 vendorItemId/itemId, 알리 sku_id, eBay var …)를 `variant` 로 저장.
  (user_id, url, variant) 가 유니크 — Supabase 는 생성 컬럼 `variant_key = coalesce(variant,'')` 에 제약(008). **등록은 조회 → 없을 때만 insert(ignore_duplicates)**: DO UPDATE 로 사용자가 고친 제목·verified·구매 상태를 덮어쓰지 않는다. SQLite 도 NULL variant 를 조회로 막는다.
  웹 `format.parseVariant` 와 워커 `models.parse_variant` 를 항상 같이 고칠 것.
- **판매자 변경** = 이력의 최빈 판매자와 현재 판매자가 다르면 알림 `note` 에 "판매자 변경: A → B". 알림은 그대로 나감.
- 사이트 추가 = `worker/worker/adapters/` 에 `BaseAdapter` 상속 파일 하나 + `registry.py` 한 줄. 다른 파일 건드리지 않기.
  `min_interval_hours`(상품별 최소 재조회 간격, 실패한 조회도 `last_fetched_at` 을 갱신해 차단된 사이트를 매시간 두드리지 않음), `budget_per_run`(실행당 호출 상한) 으로 API 한도를 지킨다.
  어댑터가 돌려준 통화가 등록 시 추정(`detect_site`)과 다르면 `products.currency` 를 따라 바꾼다(generic 사이트의 KRW 페이지 등).
- 공식 API 가 있는 사이트는 API 우선. 스크래핑 어댑터는 저빈도·사용자 등록 상품만.
- 쿠팡: 상품 ID 조회 API 가 없어 **상품명 검색 → productId 매칭**. 등록 시 상품명 필수. 실행당 8회, 6시간 간격.
- 네이버: 쇼핑 검색 API 2026-07 종료, 9월부터 검색 API 결과 AI 활용 금지 → API 미사용. 스마트스토어/브랜드스토어 페이지의
  `__PRELOADED_STATE__` 를 읽는 `adapters/naver.py`(12시간 간격, 실행당 20회)만 사용. 가격비교(search.shopping)는 지원 안 함.
- **robots.txt 준수**: 스크래핑 어댑터(naver, jsonld)는 `robots.allowed(url)` 이 False 면 AdapterError 로 스스로 중단.
- **북마클릿 캡처** (`web/src/lib/bookmarklet.ts` → `/capture` 라우트 → `api.capture`): 사용자 브라우저가 페이지에서 가격을 읽어
  앱에 기록. 봇 차단 사이트(네이버·쿠팡·아마존)의 공식 대안. seller 는 "직접 기록". 워커 어댑터와 판정 규칙은 동일.
- **정품 리스크** (`worker/risk.py` ↔ `web/src/lib/risk.ts` 규칙 동일): 확정 판정이 아니라 신호의 합. 제목 키워드(강: 레플/미러급/S급/1:1 +60,
  약: 호환/벌크/리퍼/병행/중고 +15), 자체 기준선 대비 -35/-50/-65% (+20/40/60), 같은 model_no·같은 통화 다른 상품 중앙값 대비 -25/-40/-60% (+20/40/60),
  공식 판매자(-20) / 공식→제3자 전환(+30) / 비공식(+10), **판매자 이력** 90일 내 변경 3회↑ +15 / 5회↑ +25 (`baseline.seller_changes` ↔ `risk.countSellerChanges`, 공식 판매자면 무시),
  해외 오픈마켓(+15), 제목에 모델명 없음(+10). 60↑ high, 30↑ medium.
  사용자가 `verified`(정품 확인됨) 표시하면 항상 low. high 이면 급락 알림 note 에 "판매자를 확인하세요" 경고 첨부. UI 문구는 반드시 "리스크/의심" — "짝퉁 확정" 표현 금지.
  model_no 가 없으면 `guess_model_no(title)` 로 추정(예: WH-1000XM6, OLED65C5).
- **크로스보더 실구매가** (`worker/landed.py` ↔ `web/src/lib/landed.ts` 동일, 환율은 `fx.py`/`fx.ts` — open.er-api.com 무료·키 불필요, 6시간 캐시, 실패 시 폴백 상수):
  원산지 US(amazon/ebay/walmart/bestbuy/target/etsy) / CN(알리/테무/쉬인/타오바오/티몰/JD/1688) / KR. 면세 한도 물품가 미국발 $200, 그 외 $150.
  초과 시 관세 = (물품가+배송비)×카테고리율, 부가세 = (과세가+관세)×10%. 카테고리(관세율, 미국/중국발 배송비 USD): 전자 0%/18/0, 의류 13%/15/2, 신발 13%/18/3,
  화장품 6.5%/12/2, 식품 30%/25/5, 장난감 8%/15/2, 가방 8%/15/3, 기타 8%/15/3. `products.category` (기본 전자). UI 는 항상 "추정" 표기.
  상세 "어디서 사는 게 가장 싼가" = 같은 모델 묶음을 최종가로 정렬(리스크 high 는 맨 아래, 최저 배지 제외).
- **세일 캘린더·구매 타이밍** (`web/src/lib/sales.ts` ↔ `worker/sales.py` 동일, 정적): 국가/사이트/카테고리 스코프 이벤트(광군제·블프·프라임데이·11절·618·설/추석 …).
  급락 중이면 "지금 사도 됨", 30일 내 강도 2↑ 세일이면 "N일 뒤 X — 기다려볼 만함", 그 외 중립. 실제 하락폭 데이터가 쌓이면 점수로 승격 예정.
- **안드로이드 공유 대상**: manifest `share_target` → `/share` 가 url/text 에서 링크를 뽑아 `/add?url=&title=` 로. iOS 는 북마클릿.
- **배포**: `web/vercel.json` 의 SPA rewrite 가 있어야 `/p/:id`, `/s/:token`, `/capture`, `/share` 딥링크가 새로고침·공유 시 404 가 안 난다. 로그인 게이트는 `App.tsx` 라우터 안(`/s/` 만 예외).
- **CSV 백업/이전** (`web/src/lib/csv.ts`): 열 url,variant,title,site,currency,category,captured_at,price,list_price,seller,in_stock. 가져오기는 같은 URL 에 합침.
- **구매 결정** (`worker/decision.py` ↔ `web/src/lib/decision.ts` 동일): 모든 신호를 verdict 하나로. avoid(리스크 high) > buy(목표가 도달 or 급락 & 가짜 아님; 단 30일 추세 ≤ -8% 면 wait "더 떨어지는 중") > wait(30일 내 큰 세일) > neutral.
  headline + reasons(평소 대비 %, 목표가, 가짜, 리스크, 최종가 순위, 추세, 세일). 카드·상세 최상단·알림 note 에 들어감. 새 신호를 만들면 여기에 합칠 것.
- **목표가** `products.target_price` — 이하가 되면 `kind=target` (drop 보다 우선). 상세 슬라이더(기준선의 50~100%, 추천 -15%).
- **구매 기록** `purchased_at/purchased_price` — 기록 시 active=false, 워커는 구매 상품을 건너뜀. 절약액 = max(0, 기준선 − 구매가) → 홈 "최근 30일 절약"(KRW 환산). 나중에 타이밍 점수의 정답지.
- **태그** `products.tags` (Supabase text[], SQLite 는 쉼표 문자열) — 홈 필터.
- **30일 추세** (`web/src/lib/trend.ts` ↔ `worker/trend.py` 동일): 선형회귀 기울기 → 30일 변화율, **R² < 0.6 이면 추세 없음**(평평하다 오늘 뚝 떨어진 계단식 세일을 "더 떨어지는 중"으로 오인 방지). |5%| 이상이면 배지, ≤ -8% 면 결정이 wait. 워커 알림 note 의 결정 문장도 세일·추세를 반영.
- **주간 리포트** (`worker/report.py` ↔ `web/src/lib/report.ts` 동일): 사용자별 지난 7일 = 알림 수(종류별) · 지금 사도 됨(목표가 도달 or 급락, 리스크 high 제외, 최신 스냅샷이 품절·suspect 면 제외) · 목표가 근접(5% 이내) ·
  30일 내 강도 2↑ 세일(해당 상품 수) · 이번 주 구매·절약액(KRW) · 리스크 high · 중단 상품. `python -m worker report [--dry-run]`, 월요일 09:00 KST 크론. 텔레그램·이메일은 전문, 푸시는 한 줄.
  앱은 알림 탭 상단 카드로 같은 내용을 보여준다. 항목을 추가하면 양쪽 다 고칠 것.
- 웹 결정·목표가 판정은 워커 `judge` 처럼 **품절·확인 대기(suspect) 스냅샷이면 신호 없음** (`api.ts overview/enrich` 의 `judged`). 표시용 할인율은 그대로 보여준다.
- 카드 규칙: 결정 한 줄 + 배지 최대 2개(우선순위: 구매/중단 > 리스크 > 목표가 > 확인대기 > 가짜할인 > 급락 > 역대최저 > 추세 > 실패). 상세는 요약/추이/비교/알림 탭.
  차트 마커: 알림(점), 세일 이벤트(보라 세로선), 판매자 변경(주황 세로선), 목표가(초록 가로선).
- **다나와** `adapters/danawa.py`: JSON-LD → 최저가 블록 정규식 → OG 순 폴백. **실제 페이지 미검증**(합성 HTML 테스트만). 12시간 간격. 실패 누적 시 자동 중단·북마클릿 안내.
- **실데이터 타이밍** (`sales.ts` `eventStats`): 이력 범위 안 세일 이벤트 창의 최저가 vs 직전 30일 중앙값 → "2026년 추석 ▼8%". 상세 요약 탭에 표시. 데이터가 쌓이면 buyTiming 의 근거로 승격할 것.
  `purchaseReport`: 구매가 vs 구매 후 최저가 → 잘 샀어요(-2%↑) / 무난 / 조금 일렀어요(-8%↓).
- **Chrome 확장** (`extension/`): `node extension/build.mjs` 로 `web/src/lib/bookmarklet.ts` 의 SRC 에서 `content.js` 생성 — 추출 로직은 한 곳(bookmarklet.ts)만 고친다.
  content script 는 isolated world 라 `window.__PRELOADED_STATE__` 를 못 보므로 script 텍스트에서 파싱(`st()`). 상품 페이지로 보이면 우측 하단 📌 버튼, 툴바 아이콘도 동일. 옵션에서 앱 주소 설정.
- `python -m worker doctor`: 저장소·마이그레이션·알림 채널·어댑터 활성·환율 점검. 키를 넣고 이걸 먼저 돌린다.
- Keepa(Amazon)는 유료라 미사용.
- 알림 채널 추가 = `notify.py` 에 함수 하나 + `dispatch` 등록. 만료된 푸시 구독(404/410)은 자동 삭제.

## 개발 명령

```bash
# 프런트
cd web && npm install && npm run dev        # http://localhost:5173 (Supabase 키 없으면 데모 모드)
npm run build

# 워커
cd worker && pip install -r requirements.txt
python -m worker demo                       # 데모 상품 7개·90일 이력 시드 (SQLite: worker/data/dev.db)
python -m worker run                        # 1회 수집·판정·알림
python -m worker add "<상품 URL>" [--title "상품명"]   # 쿠팡은 --title 필수
python -m worker list                       # 상품·최근가·실패 횟수
python -m worker vapid                      # 웹푸시 VAPID 키 생성 (무료)
python -m worker doctor                     # 키·연결·어댑터 상태 점검
python -m worker digest --dry-run           # 대기 알림 모아 발송 (아침·점심·저녁 크론)
python -m worker report --dry-run           # 주간 요약 리포트 (--dry-run 은 출력만)
pytest                                      # 78개 (+ PG_BIN=<postgres bin> 이면 마이그레이션 실검증 3개: tests/test_migrations.py, psycopg 필요)

# Chrome 확장
node extension/build.mjs                    # content.js 재생성 → chrome://extensions 개발자 모드로 로드
```

## 환경 변수 (`.env.example` 참고)

- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (워커) / `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (웹) — 없으면 각각 SQLite / 데모 모드
- `VITE_LOGIN_EMAIL`, `VITE_LOGIN_PASSWORD` (웹, 개인용 자동 로그인) — 있으면 세션 없을 때 `signInWithPassword` 로 스스로 로그인, 이메일 입력 화면은 실패 시에만. 계정은 `python -m worker user <email> <pw>` (admin API, 이메일 확인 완료).
- 웹푸시: `VITE_VAPID_PUBLIC_KEY` (웹), `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (워커)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` / `SMTP_*`, `ALERT_EMAIL_TO`
- 사이트 API 키(전부 무료): `COUPANG_ACCESS_KEY/SECRET_KEY`, `EBAY_CLIENT_ID/SECRET`, `BESTBUY_API_KEY`, `ELEVENST_API_KEY`, `ALIEXPRESS_APP_KEY/SECRET`

## 데이터 모델

products(variant, fail_count, last_error, last_fetched_at, verified, risk_level, risk_reasons, category, target_price, tags, purchased_at, purchased_price) → price_snapshots(price, list_price, seller, in_stock, suspect) → alerts(kind, note).
user_settings(threshold_pct, window_days, notify_push/email/telegram, digest, instant_target). shares(token, user_id, tag, name). push_subscriptions(endpoint, p256dh, auth).

## 코딩 컨벤션

- TS: 함수형 컴포넌트, 상태는 Zustand `useStore`, 데이터 접근은 `src/lib/api.ts` 만 통해서. 판정 로직은 `src/lib/format.ts` 가 워커와 동일해야 함.
- Python: 타입힌트, dataclass, 어댑터는 `BaseAdapter` 상속. 네트워크는 `httpx`. 순수 판정 로직은 `baseline.py` 에만, 테스트는 `pytest`.
- 한국어 UI, 통화는 상품 원 통화로 표시 + 해외 상품은 ≈ 한국 도착 최종가(KRW) 병기.

## 로드맵 (docs/Shopping_Helper_구상안_v0.1.md)

v0.1 프로토타입 → v0.2 쿠팡·웹푸시·가짜할인·옵션분리 → v0.3 네이버 어댑터·robots 준수·북마클릿 캡처 → v0.4 정품 리스크 점수 → v0.5 극단값 확인·자동 중단·크로스보더·세일 캘린더·공유·CSV → v0.6 구매 결정 카드·목표가·구매/절약액·태그·추세·UI 개편 → v0.7 doctor·다나와 어댑터·실데이터 타이밍·구매 성적표·Chrome 확장 → **v0.8 (현재)** 판매자 이력 신호·주간 리포트·워커 세일/추세 동기화 → **Supabase 연결·배포·실제 API 키·텔레그램 봇 (사용자)** → v0.9 가족 공유·구매 데이터 기반 타이밍 점수·실사용 튜닝 → 수익화
