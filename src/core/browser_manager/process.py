"""进程与显示原语 — Chrome 启动参数、端口/Xvfb 等待、实例 key 清洗。"""

import os
import socket
import subprocess
import time as _time
from typing import List, Optional

from loguru import logger

from src.config.settings import (
    CHROME_RENDER_MODE,
    HEADLESS_MODE,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from src.core.fingerprint import FingerprintManager

XVFB_DISPLAY = ":99"
DEBUG_PORT = 9222

# 默认实例的 key（无指纹画像时使用）
DEFAULT_KEY = "default"


def build_chrome_args(
    profile_name: Optional[str],
    user_data_dir: str,
    port: int,
    screen_size: Optional[tuple[int, int]] = None,
) -> List[str]:
    """根据指纹 profile 构建 Chrome 启动参数（实例级 user_data_dir + 端口）。"""
    os.makedirs(user_data_dir, exist_ok=True)
    fp = FingerprintManager(profile_name)
    args: List[str] = []
    if HEADLESS_MODE:
        args.append(HEADLESS_MODE)
    win_w, win_h = screen_size or (WINDOW_WIDTH, WINDOW_HEIGHT)
    args.extend(
        [
            f"--user-data-dir={user_data_dir}",
            "--no-sandbox",
            "--no-zygote",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--window-size={win_w},{win_h}",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--metrics-recording-only",
            "--password-store=basic",
            "--disable-component-extensions-with-background-pages",
            "--disable-component-update",
            "--disable-breakpad",
            f"--disk-cache-dir={user_data_dir}/cache",
            "--disk-cache-size=536870912",
            "--media-cache-size=536870912",
            "--lang=zh-CN",
            "--accept-lang=zh-CN,zh,en-US,en",
        ]
    )
    if CHROME_RENDER_MODE == "swiftshader":
        args.extend(
            [
                "--disable-gpu",
                "--use-angle=swiftshader-webgl",
                "--use-gl=swiftshader-webgl",
                "--enable-unsafe-swiftshader",
            ]
        )
    elif CHROME_RENDER_MODE == "vulkan":
        # 不强制 use-angle，让 Chrome 选默认 ANGLE 后端（构建机 headless 实测
        # 此配置下 WebGL caps 可被 fp_config 覆盖，attribs=16）。仅需
        # --enable-unsafe-swiftshader 绕过 WebGL 黑名单。
        args.extend(["--enable-unsafe-swiftshader"])
    args.extend(fp.get_browser_args())
    disable_features = set(fp.get_disable_features())
    disable_features.update(
        [
            "OptimizationHints",
            "NetworkPrediction",
            "OfflinePagesPrefetching",
            "InterestFeedContentSuggestions",
            "MediaRouter",
            "AutofillServerCommunication",
            "Translate",
        ]
    )
    if disable_features:
        args.append(f"--disable-features={','.join(sorted(disable_features))}")
    return args


def wait_for_port(port: int, timeout: int = 10) -> bool:
    """等待 Chrome 端口可用。"""
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            _time.sleep(0.5)
    return False


def _wait_for_xvfb_socket(display: str, timeout: int = 10) -> bool:
    """等待 Xvfb 的 Unix socket 就绪。"""
    socket_path = f"/tmp/.X11-unix/X{int(display.lstrip(':'))}"
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if os.path.exists(socket_path):
            return True
        _time.sleep(0.5)
    return False


def start_xvfb(display: str, screen_size: Optional[tuple[int, int]] = None) -> Optional[subprocess.Popen[bytes]]:
    """确保指定 display 的 Xvfb 可用，返回本进程启动的 Xvfb（已存在则返回 None）。

    返回 None 表示该 display 已有存活 Xvfb（共享/复用），调用方不应在关闭时终止它。
    注意：socket 文件可能是残留（Xvfb 已被强杀但 /tmp/.X11-unix/Xn 还在），
    必须以进程是否存活为准，否则会误判"已在运行"导致 Chrome 报 Missing X server。
    screen_size 允许按指纹画像指定屏幕分辨率（默认用全局 WINDOW_SIZE）。
    """
    alive = False
    try:
        result = subprocess.run(["pgrep", "-f", f"Xvfb {display}"], capture_output=True)
        alive = result.returncode == 0
    except Exception:
        alive = os.path.exists(f"/tmp/.X11-unix/X{int(display.lstrip(':'))}")
    if alive:
        return None
    # 清除残留 socket / lock 后启动
    for stale in (
        f"/tmp/.X11-unix/X{int(display.lstrip(':'))}",
        f"/tmp/.X{int(display.lstrip(':'))}-lock",
    ):
        try:
            if os.path.exists(stale):
                os.remove(stale)
        except Exception as e:
            logger.debug(f"清除残留 X11 文件 {stale} 失败(可忽略): {e}")
    w, h = screen_size or (WINDOW_WIDTH, WINDOW_HEIGHT)
    proc = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", f"{w}x{h}x24", "-ac"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_xvfb_socket(display)
    return proc


def sanitize_key(key: str) -> str:
    """把 profile_id 转成安全的目录名。"""
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return out[:80] or "profile"
