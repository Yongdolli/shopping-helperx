# GitHub · 배포 체크리스트

## 1. 올리기
폴더의 `push-to-github.cmd` 더블클릭 → 저장소 주소 입력. (git 이 없으면 https://git-scm.com 설치)
`.env`, `.env.local`, `env.txt`, `env.local.txt`, `node_modules`, `dist`, SQLite 는 `.gitignore` 로 제외됩니다 — 키가 올라가지 않습니다.

## 2. Actions Secrets (워커를 매시간 돌리기 위해)
저장소 → Settings → Secrets and variables → Actions → **New repository secret**. 이름은 정확히, 값은 `worker\.env` 에서 복사.

| 이름 | 필수 | 비고 |
|---|---|---|
| `SUPABASE_URL` | 필수 | |
| `SUPABASE_SERVICE_KEY` | 필수 | service_role 키 |
| `VAPID_PUBLIC_KEY` | 푸시 | env.txt 에 이미 있음 |
| `VAPID_PRIVATE_KEY` | 푸시 | env.txt 에 이미 있음 |
| `VAPID_SUBJECT` | 푸시 | `mailto:jiyongseog@gmail.com` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | 선택 | |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO` | 선택 | |
| `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY` | 선택 | |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | 선택 | |
| `BESTBUY_API_KEY` | 선택 | |
| `ELEVENST_API_KEY` | 선택 | |
| `ALIEXPRESS_APP_KEY`, `ALIEXPRESS_APP_SECRET` | 선택 | |

비워 둔 선택 항목은 등록하지 않아도 됩니다(빈 값으로 동작). 등록 후 **Actions 탭 → collect-prices → Run workflow** 로 한 번 수동 실행해 초록불을 확인하세요. 이후 매시 17분(UTC)에 자동 실행됩니다.

워크플로는 세 개입니다: `collect-prices`(매시 수집·판정, 알림은 저장), `daily-digest`(08:00·12:30·19:00 KST 에 대기 알림을 모아 발송), `weekly-report`(월요일 09:00 KST 주간 요약). 모두 같은 Secrets 를 씁니다. 각각 한 번 수동 실행해 메시지가 오는지 확인하세요.

> 크론은 GitHub 부하에 따라 몇 분에서 수십 분 늦게 돌 수 있습니다. 정확한 시각이 중요하면 나중에 Supabase Edge Function 또는 집 PC 의 작업 스케줄러로 옮기세요.

## 3. 웹 배포 (Vercel, 무료)
1. https://vercel.com/new → GitHub 저장소 Import
2. Root Directory 는 그대로 두어도 됩니다 — 루트의 `vercel.json` 이 `web/` 을 빌드합니다 (직접 `web` 으로 바꿔도 동작).
3. Environment Variables 에 `web\.env.local` 의 5개 (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_VAPID_PUBLIC_KEY`, `VITE_LOGIN_EMAIL`, `VITE_LOGIN_PASSWORD`) 입력
4. Deploy → 나온 주소(예: `https://shopping-helper.vercel.app`)를
   - Supabase → Authentication → URL Configuration → Site URL / Redirect URLs 에 추가 (이메일 로그인 링크용)
   - Chrome 확장 옵션의 "앱 주소"에 입력
   - 폰에서 열어 홈화면에 추가 → 설정에서 웹푸시 "켜기"
5. 이후 `git push` 만 하면 Vercel 이 자동 재배포

## 4. 순서 요약
Supabase 프로젝트 → SQL Editor 에서 `supabase/migrations/001~009` 순서대로 실행 → `setup-env.cmd` → 키 입력 → `python -m worker doctor` → `push-to-github.cmd` → Secrets → Actions 수동 실행(3개) → Vercel
