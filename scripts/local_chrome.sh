#!/bin/bash
# 在本地机器（有真实 GPU）上启动 Chrome，暴露 CDP 给内网。
# 同内网下服务器直接设置 REMOTE_CHROME_ADDRESS=<本机IP>:9222

PORT="${1:-9222}"
CHROME="/opt/google/chrome/google-chrome"

echo "Chrome CDP 暴露在 0.0.0.0:$PORT"
echo "服务器设置: REMOTE_CHROME_ADDRESS=<本机IP>:$PORT"

"$CHROME" \
    --remote-debugging-port=$PORT \
    --remote-debugging-address=0.0.0.0 \
    --remote-allow-origins="*" \
    --disable-blink-features=AutomationControlled \
    --window-size=1920,1080 \
    --user-data-dir="/tmp/chrome-remote-profile" \
    about:blank
