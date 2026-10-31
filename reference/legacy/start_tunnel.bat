@echo off
chcp 65001 >nul
rem 봇 서버(9000번 포트)를 인터넷에서 접속할 수 있는 https 주소로 열어 줌 (Cloudflare 임시 터널, Windows용)
rem 다시 실행할 때마다 주소가 바뀝니다.

set PORT=9000

where cloudflared >nul 2>nul
if errorlevel 1 (
  echo cloudflared 가 설치되어 있지 않습니다. 아래 명령으로 설치한 뒤, 새 창에서 다시 실행하세요.
  echo     winget install --id Cloudflare.cloudflared
  pause
  exit /b 1
)

echo 포트 %PORT% 를 공개 주소로 여는 중...
echo 아래에 나오는 https://...trycloudflare.com 주소 뒤에 /kakao/webhook 을 붙여 웹훅 URL에 등록하세요.
cloudflared tunnel --no-autoupdate --url http://localhost:%PORT%
