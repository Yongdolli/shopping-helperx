@echo off
REM Shopping Helper - 미리 채워둔 환경 파일을 실제 이름으로 복사합니다 (한 번만 실행)
cd /d "%~dp0"
if exist web\.env.local (echo web\.env.local 이미 있음 - 건너뜀) else (copy /Y web\env.local.txt web\.env.local >nul && echo web\.env.local 생성됨)
if exist worker\.env (echo worker\.env 이미 있음 - 건너뜀) else (copy /Y worker\env.txt worker\.env >nul && echo worker\.env 생성됨)
echo.
echo 이제 web\.env.local 과 worker\.env 를 열어 [필수] 항목에 키만 붙여넣고 저장하세요.
pause
