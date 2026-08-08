"""指纹环境变量 — 时区检测与基础 FP_* 兜底值。"""

import json
import os
import urllib.request
from typing import Any, Dict

from src.config.settings import (
    DEFAULT_UA,
    DEFAULT_UA_BRAND,
    DEFAULT_UA_FULL,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)


def _detect_timezone() -> str:
    """根据出口 IP 检测时区，避免硬编码 TZ 与 IP 地理位置不一致（指纹一致性）。

    Cloudflare 等会比对「IP 时区 vs 本地时区」，TZ 必须与出口 IP 匹配。
    出口 IP 变化（换节点）时自动跟随。失败时回退到继承的 TZ 或 UTC。
    """
    candidates = [
        ("https://ipapi.co/timezone/", None),
        ("https://ipinfo.io/json", "timezone"),
    ]
    for url, key in candidates:
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                raw = resp.read().decode("utf-8", "ignore").strip()
            data: Dict[str, Any] = json.loads(raw) or {}
            tz: str = str(data.get(key) or "") if key else raw
            if tz and "/" in tz and len(tz) < 40:
                return tz
        except Exception:
            continue
    return os.environ.get("TZ") or "UTC"


def base_fp_env() -> Dict[str, str]:
    """基础指纹环境变量（默认/兜底值，画像环境在此基础上覆盖）。"""
    return {
        "TZ": _detect_timezone(),
        "FP_UA": DEFAULT_UA,
        "FP_UA_FULL": DEFAULT_UA_FULL,
        "FP_UA_BRAND": DEFAULT_UA_BRAND,
        "FP_UA_GREASE": "99",
        "FP_UA_GREASE_FULL": "99.0.0.0",
        "FP_UAD_PLATFORM_VERSION": "",
        "FP_UAD_MODEL": "",
        "FP_UAD_ARCH": "x86",
        "FP_LANGS": "zh-CN,zh",
        "FP_CANVAS_NOISE": "0",
        "FP_AUDIO_NOISE": "0",
        "FP_WEBGL_VENDOR": "Google Inc. (Intel)",
        "FP_WEBGL_RENDERER": "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.5 (Core Profile) Mesa 25.0.7)",
        "FP_GL_MAX_TEXTURE_SIZE": "16384",
        "FP_WEBRTC_REPLACE_HOST_IP": "1",
        # 桌面有线网络典型值（容器无真实网络质量信号，NQE 默认会给出弱网值）
        "FP_NET_RTT": "50",
        "FP_NET_DOWNLINK": "10",
        # 屏幕尺寸与窗口/Xvfb 一致（VNC 可见性 + 指纹自洽）
        "FP_SCREEN_WIDTH": str(WINDOW_WIDTH),
        "FP_SCREEN_HEIGHT": str(WINDOW_HEIGHT),
        "FP_SCREEN_COLOR_DEPTH": "24",
    }
