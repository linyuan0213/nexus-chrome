@echo off
:: 在 Windows 本机启动 Chrome，暴露 CDP 给内网。
:: 同内网服务器设置: REMOTE_CHROME_ADDRESS=<本机IP>:9222

set PORT=%1
if "%PORT%"=="" set PORT=9222

echo Chrome CDP 暴露在 0.0.0.0:%PORT%
echo 服务器设置: REMOTE_CHROME_ADDRESS=<本机IP>:%PORT%

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=%PORT% ^
    --remote-debugging-address=0.0.0.0 ^
    --remote-allow-origins=* ^
    --disable-blink-features=AutomationControlled ^
    --window-size=1920,1080 ^
    --user-data-dir="%TEMP%\chrome-remote-profile" ^
    about:blank

echo Chrome 已启动
pause
