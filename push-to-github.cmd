@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo  Shopping Helper - GitHub 올리기
echo ============================================
echo.
echo 먼저 https://github.com/new 에서 빈 저장소(Private 권장)를 만들고, 그 주소를 붙여넣으세요.
echo 예: https://github.com/jiyongseog/shopping-helper.git
set /p REPO=저장소 주소: 
if "%REPO%"=="" (echo 주소가 비었습니다. & pause & exit /b 1)

where git >nul 2>nul || (echo git 이 없습니다. https://git-scm.com 에서 설치 후 다시 실행하세요. & pause & exit /b 1)

REM GitHub Actions 워크플로를 정식 위치로 (원격 도구가 .github 에 못 써서 임시 폴더에 있었음)
if exist github-workflows (
  if not exist .github\workflows mkdir .github\workflows
  move /Y github-workflows\*.yml .github\workflows\ >nul
  rmdir github-workflows 2>nul
  echo .github\workflows\ 에 collect.yml, daily-digest.yml, weekly-report.yml 배치 완료
)

if not exist .git (
  git init -b main >nul
  echo git 저장소 초기화
)
git add -A
git -c user.name="Yongseog Ji" -c user.email="jiyongseog@gmail.com" commit -m "Shopping Helper v0.8" >nul 2>nul || echo (변경 없음 - 커밋 건너뜀)
git remote remove origin >nul 2>nul
git remote add origin "%REPO%"
git push -u origin main
if errorlevel 1 (
  echo.
  echo 푸시 실패 - GitHub 로그인 창이 떴다면 로그인 후 다시 실행하세요.
  pause & exit /b 1
)
echo.
echo [OK] 올라갔습니다. 다음 단계:
echo   1. GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret
echo      GITHUB.md 의 목록대로 등록 (worker\.env 값을 그대로 복사)
echo   2. Actions 탭 → collect-prices, daily-digest, weekly-report → Run workflow 로 각각 1회 수동 실행해 성공 확인
echo   3. https://vercel.com/new 에서 이 저장소 Import → Root Directory = web → 환경 변수 3개 입력 → Deploy
pause
