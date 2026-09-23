# 다음 할 일 (Claude Code 이어서 작업)

> Claude Code 시작 시: `CLAUDE.md` 먼저 읽기. 현재 v0.9(딜 피드), 실 PostgreSQL 마이그레이션 검증 포함·빌드 통과 (2026-09-08).
> **사용자 할 일 (2026-09-24)**: Supabase SQL Editor 에서 `supabase/migrations/012_deal_sends.sql` 실행(다이제스트 중복 방지). 쿠팡 시세를 쓰려면 파트너스 키를 GitHub Secrets(`COUPANG_ACCESS_KEY/SECRET_KEY`)에.
> 원칙: 전부 무료. API 키는 사용자가 직접 연결.

## 1단계 — 사용자 손이 먼저 필요한 것 (연결)

- [x] **Supabase** 프로젝트 생성 → SQL Editor 에 `supabase/ALL_MIGRATIONS.sql`(001~009 합본) 전체를 붙여넣고 Run (또는 개별 파일을 번호 순서대로) → Auth → Email(매직링크) 켜기
- [x] 폴더의 `setup-env.cmd` 실행 → `web/.env.local`, `worker/.env` 생성됨 → **[필수]** Supabase URL / anon key / service key 붙여넣기 (웹푸시 키는 이미 들어 있음)
- [x] `cd worker && pip install -r requirements.txt && python -m worker doctor` → 초록 항목 확인
- [x] 자동 로그인 계정 생성 (`python -m worker user …`, 2026-09-08) — 이메일 입력 없이 앱이 열리면 로그인됨
- [ ] `cd web && npm run dev` → 자동 로그인 → 상품 1개 등록 → 데모 모드가 아닌지 확인

## 2단계 — 배포·자동 수집

- [x] `push-to-github.cmd` → https://github.com/Yongdolli/shopping-helperx (2026-09-08) → GitHub → Settings → Secrets 에 `GITHUB.md` 표대로 등록 (최소 SUPABASE_URL, SUPABASE_SERVICE_KEY, VAPID_*)
- [ ] Actions 탭 → `collect-prices` → Run workflow 수동 1회 → 로그에서 에러 없는지 확인 (이후 매시 17분 자동)
- [ ] Actions 탭 → `daily-digest` → Run workflow 수동 1회 → 대기 알림이 있으면 "🌅/☀️/🌙 알림 N건" 도착 확인 (이후 08:00·12:30·19:00 KST 자동). 로컬: `python -m worker digest --dry-run`
- [ ] Actions 탭 → `weekly-report` → Run workflow 수동 1회 → 텔레그램/이메일에 "📋 주간 요약" 도착 확인 (이후 월요일 09:00 KST 자동). 로컬 미리보기: `python -m worker report --dry-run`
- [x] **Vercel** https://shopping-helperx.vercel.app — Import → Root Directory `web` → env 5개(`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_VAPID_PUBLIC_KEY`, `VITE_LOGIN_EMAIL`, `VITE_LOGIN_PASSWORD`) → 배포
- [ ] Supabase → Auth → URL Configuration → Site URL / Redirect 에 Vercel 주소
- [ ] 폰: 배포 주소 접속 → 홈 화면에 추가 → 설정에서 웹푸시 "켜기" → 쇼핑 앱에서 "공유 → Shopping Helper" 되는지
- [ ] PC: `node extension/build.mjs` → chrome://extensions 개발자 모드 → `extension/` 로드 → 옵션에 배포 주소

## 3단계 — 사이트 연결 (무료 키)

- [ ] 쿠팡 파트너스 / eBay 개발자 / Best Buy / 11번가 OpenAPI / 알리익스프레스 Affiliate 키 → `worker/.env` (주석에 발급 URL 있음) → `python -m worker doctor` 재확인 → GitHub Secrets 에도 등록
- [ ] 실상품으로 검증: 네이버 스마트스토어·다나와 어댑터가 실제 페이지에서 동작하는지 (**다나와는 합성 HTML 로만 테스트됨**). 차단되면 북마클릿/확장으로 대체
- [ ] 텔레그램: BotFather 로 봇 생성 → `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- [ ] Gmail 앱 비밀번호 → `SMTP_PASS`

## 4단계 — 개발 (Claude Code)

실데이터가 쌓인 뒤에 가치 있는 것부터:

- [ ] 실사용에서 나온 버그·오탐 수정 (극단값 확인, 가짜할인 기준, 리스크 점수 튜닝)
- [x] 판매자 이력 신호 (v0.8: 90일 내 변경 3회↑ +15 / 5회↑ +25) — 실데이터로 임계값 튜닝 필요
- [ ] 구매 데이터 기반 타이밍 점수 승격 (`purchaseReport` → 카테고리별 "이 시기에 사면 평균 N% 절약")
- [x] 주간 요약 리포트 (v0.8: `worker report` + `weekly-report.yml` + 앱 알림 탭 카드)
- [x] 가족 공유 (v0.8: 태그 단위 읽기 전용 링크 `/s/<token>`, security definer RPC) — 실환경에서 anon 열람·RLS 확인 필요
- [ ] 에누리 어댑터, Amazon 은 Keepa 유료라 보류 (북마클릿/확장으로만)
- [ ] Chrome 웹스토어 등록 시 `<all_urls>` → 도메인 목록으로 권한 축소
- [ ] pywebpush 가 PC 에서 설치되는지 확인 (샌드박스에선 setuptools 문제로 미설치)

## 미검증 목록 (실환경에서 확인 필요)

다나와 어댑터 · 네이버 어댑터 실페이지 · 실제 푸시 전송 · API 어댑터 5종(키 없음) · GitHub Actions 실행(collect·daily-digest·weekly-report) · Vercel 빌드 · (마이그레이션 SQL 은 임베디드 PostgreSQL 로 검증 완료) · 주간 리포트 실제 텔레그램/이메일 발송(Supabase 저장소 `alerts_since` 쿼리 포함) · 가족 공유 링크 anon 열람(009 RPC)
