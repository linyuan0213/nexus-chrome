#!/bin/bash

# VNC 密码检查：不允许使用默认密码部署
if [ -z "$VNC_PASSWORD" ]; then
    echo "ERROR: VNC_PASSWORD environment variable is not set." >&2
    echo "Please set a strong password for VNC access, e.g.:" >&2
    echo "  docker run -e VNC_PASSWORD=your_secure_password ..." >&2
    exit 1
fi

if [ "$VNC_PASSWORD" = "password" ]; then
    echo "ERROR: VNC_PASSWORD cannot be the default value 'password'." >&2
    exit 1
fi

export VNC_PASSWORD

# 启动 supervisord
exec supervisord -c /etc/supervisord.conf
