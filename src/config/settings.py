"""应用配置和设置"""

import os
import platform
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.scripts import CLICK_RANDOMIZE_JS

_IS_WINDOWS = platform.system() == "Windows"
_DEFAULT_CHROME = (
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" if _IS_WINDOWS else "/opt/google/chrome/google-chrome"
)

# ============================================================
# 浏览器 JS 脚本
# ============================================================

# 点击坐标随机化 JS


# 完整指纹伪装 JS


# ============================================================
# 挑战检测配置
# ============================================================

CHALLENGE_TITLES: List[str] = [
    "Just a moment...",
    "请稍候…",
    "DDOS-GUARD",
]

CHALLENGE_SELECTORS: List[str] = [
    "#cf-challenge-running",
    ".ray_id",
    ".attack-box",
    "#cf-please-wait",
    "#challenge-spinner",
    "#trk_jschal_js",
    "td.info #js_info",
    "div.vc div.text-box h2",
]

CHALLENGE_BOX_SELECTORS: List[str] = ['input[name="cf-turnstile-response"]']

# Cloudflare 专用
CF_CHALLENGE_SELECTORS: List[str] = CHALLENGE_SELECTORS
CF_BOX_SELECTORS: List[str] = CHALLENGE_BOX_SELECTORS

# 五秒盾
FIVE_SECOND_SELECTORS: List[str] = [
    "#sec",
    ".loading-countdown",
    ".countdown-timer",
    "#wait-time",
    'span[class*="second"]',
    'div[class*="countdown"]',
]

# 雷池
LEICHI_SELECTORS: List[str] = [
    "#safeline-block",
    'div[class*="safeline"]',
    'meta[name="safeline"]',
    'input[name="__safeline_"]',
    'script[src*="safeline"]',
    ".safeline-challenge",
]

# 通用挑战
GENERIC_CHALLENGE_SELECTORS: List[str] = [
    "#challenge-running",
    ".challenge-container",
    ".verification",
    ".captcha-container",
    "#recaptcha",
    ".g-recaptcha",
    "[data-challenge]",
]

# 挑战类型常量
CHALLENGE_TYPE_CLOUDFLARE = "cloudflare"
CHALLENGE_TYPE_CLOUDFLARE_BOX = "cloudflare_box"
CHALLENGE_TYPE_FIVE_SECOND = "five_second_shield"
CHALLENGE_TYPE_LEICHI = "leichi"
CHALLENGE_TYPE_GENERIC = "generic"
CHALLENGE_TYPE_NONE = "none"

# 挑战超时与重试
CHALLENGE_TIMEOUT = int(os.getenv("CHALLENGE_TIMEOUT", "60"))
CHALLENGE_RETRY_COUNT = int(os.getenv("CHALLENGE_RETRY_COUNT", "3"))

# UA 兜底值（画像 env 未提供时使用；与 patched Chromium 发布版本保持一致）
DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
DEFAULT_UA_FULL = "153.0.7991.0"
DEFAULT_UA_BRAND = "153"

# ============================================================
# 指纹配置
# ============================================================
# 注意：JS 级指纹伪装已移除（可被检测），真正的指纹差异化走 fp_profile_id
# （C++ fp_config + BrowserPool 独立实例）。此处 default/stealth/paranoid
# 仅作为 Chrome 启动参数预设选择器，不再包含任何 JS 注入。
# ============================================================
FINGERPRINT_PROFILES: Dict[str, Dict[str, Any]] = {
    "default": {
        "name": "基础参数",
        "js_scripts": [CLICK_RANDOMIZE_JS],
        "disable_webgl": False,
        "browser_args": [],
        "disable_features": [],
    },
    "stealth": {
        "name": "标准参数（推荐）",
        "js_scripts": [CLICK_RANDOMIZE_JS],
        "disable_webgl": False,
        "browser_args": [
            "--enable-features=NetworkService,NetworkServiceInProcess,LoadCryptoTokenExtension,PermuteTLSExtensions",
            "--disable-features=FlashDeprecationWarning,EnablePasswordsAccountStorage",
            "--disable-component-extensions-with-background-pages",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-first-run",
            "--password-store=basic",
        ],
        "disable_features": [
            "FlashDeprecationWarning",
            "EnablePasswordsAccountStorage",
        ],
    },
    "paranoid": {
        "name": "禁用 WebGL",
        "js_scripts": [CLICK_RANDOMIZE_JS],
        "disable_webgl": True,
        "browser_args": [
            "--enable-features=NetworkService,NetworkServiceInProcess,LoadCryptoTokenExtension,PermuteTLSExtensions",
            "--disable-features=FlashDeprecationWarning,EnablePasswordsAccountStorage",
            "--disable-component-extensions-with-background-pages",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-first-run",
            "--password-store=basic",
            "--disable-webgl",
        ],
        "disable_features": [
            "FlashDeprecationWarning",
            "EnablePasswordsAccountStorage",
        ],
    },
}

DEFAULT_FINGERPRINT_PROFILE = "stealth"

# ============================================================
# 应用设置
# ============================================================
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "9850"))
CHROME_PATH = os.getenv("CHROME_PATH", _DEFAULT_CHROME)
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "")
REMOTE_CHROME_ADDRESS = os.getenv("REMOTE_CHROME_ADDRESS", "")  # 如 127.0.0.1:9222
BROWSER_MONITOR_INTERVAL = 10
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "100"))
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))
SESSION_CLEANUP_INTERVAL = int(os.getenv("SESSION_CLEANUP_INTERVAL", "300"))


def _read_version() -> str:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with open(pyproject, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (OSError, KeyError):
        return "0.0.0"


APP_VERSION = os.getenv("APP_VERSION", _read_version())
# 多指纹并发实例上限（每个指纹一个 Chrome 进程，约 0.5-1GB 内存/实例）
MAX_BROWSERS = int(os.getenv("MAX_BROWSERS", "5"))
PROFILE_DATA_DIR = os.getenv(
    "PROFILE_DATA_DIR", os.path.join(os.path.expanduser("~"), ".cache", "nexus-chrome", "profiles")
)

# 会话持久化数据目录（sessions.json 等）
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.getcwd(), "data"))
WINDOW_SIZE = os.getenv("WINDOW_SIZE", "1920x1080")
try:
    _parsed_dims = tuple(int(x) for x in WINDOW_SIZE.lower().split("x"))
    _window_width, _window_height = _parsed_dims
except Exception:
    _window_width, _window_height = 1920, 1080
WINDOW_WIDTH = _window_width
WINDOW_HEIGHT = _window_height

USER_DATA_PATH = os.getenv(
    "USER_DATA_PATH", os.path.join(os.path.expanduser("~"), ".cache", "nexus-chrome", "user_data")
)


def _parse_bool(value: Optional[str], default: bool) -> bool:
    """把环境变量字符串解析为布尔值。"""
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# 用户数据目录清理配置
CLEANUP_ENABLED = _parse_bool(os.getenv("CLEANUP_ENABLED"), True)
CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "3600"))
CLEANUP_MAX_SIZE_GB = float(os.getenv("CLEANUP_MAX_SIZE_GB", "2.0"))
CLEANUP_MAX_AGE_SECONDS = int(os.getenv("CLEANUP_MAX_AGE_SECONDS", "0"))
CLEANUP_KEEP_COOKIES = _parse_bool(os.getenv("CLEANUP_KEEP_COOKIES"), True)

# Chrome 渲染模式：auto=由 Chrome 自动选择(去掉软件渲染参数)；swiftshader=使用 SwiftShader 软件渲染
CHROME_RENDER_MODE = os.getenv("CHROME_RENDER_MODE", "auto").strip().lower()

# 每实例 VNC（x11vnc + websockify）配置
VNC_ENABLED = _parse_bool(os.getenv("VNC_ENABLED"), True)
VNC_PASSWORD = os.getenv("VNC_PASSWORD", "password")
VNC_PORT_BASE = 5900  # x11vnc 端口基数：5900 + display_index
VNC_WEB_PORT_BASE = 6080  # websockify 端口基数：6080 + display_index
VNC_DISPLAY_BASE = 1  # Xvfb display 号基数：:1、:2、:3...
VNC_WEB_PORT_MAX = int(os.getenv("VNC_WEB_PORT_MAX", "6100"))  # websockify 端口上限

# HTTP 客户端配置
HTTP_CLIENT_TIMEOUT = int(os.getenv("HTTP_CLIENT_TIMEOUT", "30"))
HTTP_MAX_REDIRECTS = int(os.getenv("HTTP_MAX_REDIRECTS", "10"))

# 向后兼容别名

# Turnstile hook JS，在创建 tab 时通过 add_init_js 注入
with open(os.path.join(os.path.dirname(__file__), "turnstile_hook.js")) as _f:
    TURNSTILE_HOOK_JS = _f.read()
