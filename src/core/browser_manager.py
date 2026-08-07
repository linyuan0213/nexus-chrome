"""浏览器池 — 多指纹并发 Chrome 实例管理。

架构：每个指纹画像（或默认）对应一个独立的 Chrome 进程，拥有：
- 独立的 user-data-dir（cookie/localStorage/缓存完全隔离）
- 独立的调试端口（DrissionPage 独立连接）
- 独立的 FP_* 环境变量（patched Chromium 按进程读取指纹）

会话按 fp_profile_id 路由到对应实例，不同会话可同时运行不同指纹。
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import threading
import time as _time
import urllib.request
from typing import IO, Any, Dict, List, Optional

from DrissionPage import Chromium, ChromiumOptions
from loguru import logger

from src.config.settings import (
    BROWSER_MONITOR_INTERVAL,
    CHROME_PATH,
    CHROME_RENDER_MODE,
    DEFAULT_FINGERPRINT_PROFILE,
    DEFAULT_UA,
    DEFAULT_UA_BRAND,
    DEFAULT_UA_FULL,
    HEADLESS_MODE,
    MAX_BROWSERS,
    PROFILE_DATA_DIR,
    REMOTE_CHROME_ADDRESS,
    USER_DATA_PATH,
    VNC_DISPLAY_BASE,
    VNC_ENABLED,
    VNC_PASSWORD,
    VNC_PORT_BASE,
    VNC_WEB_PORT_BASE,
    VNC_WEB_PORT_MAX,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from src.core.fingerprint import FingerprintManager

XVFB_DISPLAY = ":99"
DEBUG_PORT = 9222

# 默认实例的 key（无指纹画像时使用）
DEFAULT_KEY = "default"


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


def _base_fp_env() -> Dict[str, str]:
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
        # 屏幕尺寸与窗口/Xvfb 一致（VNC 可见性 + 指纹自洽）
        "FP_SCREEN_WIDTH": str(WINDOW_WIDTH),
        "FP_SCREEN_HEIGHT": str(WINDOW_HEIGHT),
        "FP_SCREEN_COLOR_DEPTH": "24",
    }


def _build_chrome_args(
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


def _wait_for_port(port: int, timeout: int = 10) -> bool:
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


def _start_xvfb(display: str, screen_size: Optional[tuple[int, int]] = None) -> Optional[subprocess.Popen[bytes]]:
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


class ChromeInstance:
    """单个指纹的 Chrome 实例（独立进程 + 独立存储 + 独立指纹 env）。

    支持指定 chrome 二进制（patched chromium 或真实 Google Chrome），
    用于 Google 等对修改后二进制做严格检测的站点。
    """

    def __init__(
        self,
        key: str,
        fp_env: Optional[Dict[str, str]],
        user_data_dir: str,
        port: int,
        is_default: bool = False,
        chrome_path: Optional[str] = None,
        display_index: Optional[int] = None,
    ):
        self.key = key
        self.fp_env: Dict[str, str] = dict(fp_env) if fp_env else {}
        self.user_data_dir = user_data_dir
        self.port = port
        self.is_default = is_default
        self.chrome_path = chrome_path or CHROME_PATH
        # 每实例独立显示/VNC：display_index 为 None 时回退到共享 :99（无 VNC）
        self.display_index = display_index
        self.display = f":{display_index}" if display_index is not None else None
        self.vnc_port = VNC_PORT_BASE + display_index if display_index is not None else None
        self.web_port = VNC_WEB_PORT_BASE + display_index if display_index is not None else None
        self._browser: Optional[Chromium] = None
        self._chrome_proc: Optional[subprocess.Popen[bytes]] = None
        self._chrome_stderr: Optional[IO[str]] = None
        self._xvfb_proc: Optional[subprocess.Popen[bytes]] = None
        self._x11vnc_proc: Optional[subprocess.Popen[bytes]] = None
        self._websockify_proc: Optional[subprocess.Popen[bytes]] = None
        self._lock = threading.Lock()
        self._last_used = _time.monotonic()
        # 会话引用计数：>0 表示有活跃会话在使用，0 表示空闲可回收
        self.ref_count = 0
        self._idle_since: Optional[float] = None

    # ---- 引用计数 ----
    def retain(self) -> None:
        """会话关联此实例（创建会话时调用）。"""
        with self._lock:
            self.ref_count += 1
            self._idle_since = None
            self._last_used = _time.monotonic()

    def release(self) -> int:
        """会话释放此实例（删除会话时调用）。返回剩余引用数。"""
        with self._lock:
            self.ref_count = max(0, self.ref_count - 1)
            if self.ref_count == 0:
                self._idle_since = _time.monotonic()
                self._last_used = _time.monotonic()
            return self.ref_count

    @property
    def is_idle(self) -> bool:
        return self.ref_count <= 0

    @property
    def idle_seconds(self) -> Optional[float]:
        if not self.is_idle or self._idle_since is None:
            return None
        return _time.monotonic() - self._idle_since

    # ---- 状态 ----
    @property
    def browser(self) -> Chromium:
        return self.ensure()

    def reap_dead_browser(self) -> bool:
        """底层浏览器已死亡时强制 quit 并置 None（等待下次重建）。返回是否回收。"""
        browser = self._browser
        if browser is None or self.is_alive:
            return False
        with self._lock:
            try:
                browser.quit()
            except Exception as e:
                logger.debug(f"[fp:{self.key}] 关闭异常浏览器实例时出错，忽略: {e}")
            self._browser = None
        return True

    @property
    def is_alive(self) -> bool:
        try:
            if self._browser is None:
                return False
            return bool(self._browser.states.is_alive)
        except Exception:
            return False

    def touch(self) -> None:
        self._last_used = _time.monotonic()

    @property
    def last_used(self) -> float:
        return self._last_used

    # ---- 生命周期 ----
    def ensure(self) -> Chromium:
        """确保实例启动并连接 DrissionPage，返回 Chromium 对象。"""
        with self._lock:
            self.touch()
            if self._browser is not None and self._browser.states.is_alive:
                return self._browser
            if self._is_remote:
                co = ChromiumOptions()
                co.set_address(REMOTE_CHROME_ADDRESS)
                self._browser = Chromium(co)
            else:
                self._start_chrome()
                co = ChromiumOptions()
                co.set_local_port(self.port)
                self._browser = Chromium(co)
            logger.info(f"[fp:{self.key}] Chrome {self._browser.version} 就绪 (port={self.port})")
            return self._browser

    def _start_chrome(self) -> None:
        if self._chrome_proc and self._chrome_proc.poll() is None:
            return
        if self._chrome_proc is not None:
            try:
                self._chrome_proc.terminate()
                self._chrome_proc.wait(timeout=3)
            except Exception:
                logger.debug(f"[fp:{self.key}] 终止残留 Chrome 进程失败，继续启动新实例")
            self._chrome_proc = None
            # Chrome 需要重启时，先停掉旧 VNC 栈，避免端口上残留重复进程
            self._stop_vnc()
        if self.display is not None:
            self._xvfb_proc = _start_xvfb(self.display, self.screen_size)
        else:
            _start_xvfb(XVFB_DISPLAY)
        chrome = self.chrome_path or CHROME_PATH or "/opt/google/chrome/google-chrome"
        env = os.environ.copy()
        env.update(_base_fp_env())
        env["DISPLAY"] = self.display if self.display is not None else XVFB_DISPLAY
        env.update(self.fp_env)  # 画像环境覆盖基础值（FP_SCREEN_* 按画像）
        # 屏幕尺寸与画像保持一致：Xvfb 按画像尺寸，env 的 FP_SCREEN_* 也同步
        sw, sh = self.screen_size
        env["FP_SCREEN_WIDTH"] = str(sw)
        env["FP_SCREEN_HEIGHT"] = str(sh)
        # 清理残留的 Chrome 配置锁（崩溃/强杀后 SingletonLock 残留会导致拒绝启动）
        try:
            for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                lock_path = os.path.join(self.user_data_dir, lock_name)
                if os.path.exists(lock_path):
                    os.remove(lock_path)
        except Exception:
            logger.debug(f"[fp:{self.key}] 清理 Chrome 配置锁失败，继续")
        args = [
            chrome,
            *_build_chrome_args(DEFAULT_FINGERPRINT_PROFILE, self.user_data_dir, self.port, self.screen_size),
            "about:blank",
        ]
        logger.debug(f"[fp:{self.key}] 启动 Chrome 参数: {args[:6]}...")
        chrome_stderr_path = f"{self.user_data_dir}/chrome_stderr.log"
        os.makedirs(os.path.dirname(chrome_stderr_path), exist_ok=True)
        self._chrome_stderr = open(chrome_stderr_path, "w")
        self._chrome_proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=self._chrome_stderr,
            env=env,
        )
        if not _wait_for_port(self.port, timeout=30):
            logger.warning(f"[fp:{self.key}] Chrome 调试端口未在 30 秒内就绪")
        _time.sleep(1)
        self._start_vnc()

    def _start_vnc(self) -> None:
        """为该实例启动 x11vnc + websockify（独立 display → noVNC 网页端口）。"""
        if not VNC_ENABLED or self.vnc_port is None or self.web_port is None or self.display is None:
            return
        if self.web_port > VNC_WEB_PORT_MAX:
            logger.warning(f"[fp:{self.key}] websockify 端口 {self.web_port} 超过上限 {VNC_WEB_PORT_MAX}，跳过 VNC")
            return
        # 幂等：已有存活进程则跳过，避免重复启动
        if (
            self._x11vnc_proc
            and self._x11vnc_proc.poll() is None
            and self._websockify_proc
            and self._websockify_proc.poll() is None
        ):
            return
        try:
            self._x11vnc_proc = subprocess.Popen(
                [
                    "x11vnc",
                    "-display",
                    self.display,
                    "-forever",
                    "-shared",
                    "-passwd",
                    VNC_PASSWORD,
                    "-rfbport",
                    str(self.vnc_port),
                    "-listen",
                    "127.0.0.1",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.debug(f"[fp:{self.key}] 启动 x11vnc 失败: {e}")
        try:
            websockify = shutil.which("websockify") or "/app/.venv/bin/websockify"
            self._websockify_proc = subprocess.Popen(
                [
                    websockify,
                    str(self.web_port),
                    f"127.0.0.1:{self.vnc_port}",
                    "--web",
                    "/opt/noVNC",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.debug(f"[fp:{self.key}] 启动 websockify 失败: {e}")
        logger.info(f"[fp:{self.key}] VNC 就绪: display={self.display} vnc=:{self.vnc_port} web=:{self.web_port}")

    def _stop_vnc(self) -> None:
        """停止该实例的 websockify / x11vnc（供重启与关闭时复用）。"""
        for name, attr in (("websockify", "_websockify_proc"), ("x11vnc", "_x11vnc_proc")):
            proc = getattr(self, attr)
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    logger.debug(f"[fp:{self.key}] 终止 {name} 失败，继续")
                setattr(self, attr, None)

    def shutdown(self) -> None:
        """关闭实例（进程 + DrissionPage 连接 + VNC/Xvfb）。"""
        if self._browser is not None:
            try:
                self._browser.quit()
            except Exception:
                logger.debug(f"[fp:{self.key}] 关闭浏览器连接出错，继续释放资源")
            self._browser = None
        if self._chrome_proc is not None:
            try:
                self._chrome_proc.terminate()
                self._chrome_proc.wait(timeout=3)
            except Exception:
                logger.debug(f"[fp:{self.key}] 终止 Chrome 进程失败，继续")
            self._chrome_proc = None
        self._stop_vnc()
        if self._xvfb_proc is not None:
            try:
                self._xvfb_proc.terminate()
                self._xvfb_proc.wait(timeout=3)
            except Exception:
                logger.debug(f"[fp:{self.key}] 终止 Xvfb 失败，继续")
            self._xvfb_proc = None
        if self._chrome_stderr and not self._chrome_stderr.closed:
            self._chrome_stderr.close()
            self._chrome_stderr = None
        logger.info(f"[fp:{self.key}] 实例已关闭")

    @property
    def _is_remote(self) -> bool:
        return bool(REMOTE_CHROME_ADDRESS)

    @property
    def screen_size(self) -> tuple[int, int]:
        """按指纹画像的屏幕分辨率确定窗口尺寸（画像未指定则用全局 WINDOW_SIZE）。"""
        w = int(self.fp_env.get("FP_SCREEN_WIDTH") or 0) or WINDOW_WIDTH
        h = int(self.fp_env.get("FP_SCREEN_HEIGHT") or 0) or WINDOW_HEIGHT
        if w <= 0 or h <= 0:
            return WINDOW_WIDTH, WINDOW_HEIGHT
        return w, h


class BrowserPool:
    """多指纹 Chrome 实例池：按 key（profile_id / default）管理实例。"""

    def __init__(self, max_browsers: int = MAX_BROWSERS):
        self._max_browsers = max_browsers
        self._instances: Dict[str, ChromeInstance] = {}
        self._lock = threading.Lock()
        self._next_port = DEBUG_PORT
        self._next_display = VNC_DISPLAY_BASE
        self._display_reuse: set[int] = set()
        self._monitor_task: Optional[asyncio.Task[None]] = None
        self._idle_ttl = float(os.getenv("INSTANCE_IDLE_TTL", "600"))  # 空闲实例回收 TTL（秒）

    # ---- 引用计数 ----
    def retain(self, key: str) -> None:
        """会话创建时关联实例（引用 +1）。"""
        inst = self._instances.get(key)
        if inst is not None:
            inst.retain()

    def release(self, key: str) -> None:
        """会话删除时释放实例（引用 -1）；引用归零后立即关闭实例回收内存。"""
        inst = self._instances.get(key)
        if inst is None:
            return
        remaining = inst.release()
        if remaining <= 0:
            self._close_instance(key, "会话释放后无引用")

    def close_instance(self, key: str, reason: str) -> None:
        """公开接口：关闭并移除实例（供 API 手动关闭）。"""
        self._close_instance(key, reason)

    def _close_instance(self, key: str, reason: str) -> None:
        """关闭并移除实例。"""
        with self._lock:
            inst = self._instances.pop(key, None)
        if inst is not None:
            logger.info(f"[pool] 关闭实例 {key}（{reason}）")
            try:
                inst.shutdown()
            except Exception as e:
                logger.debug(f"[pool] 关闭实例 {key} 异常: {e}")
            if inst.display_index is not None:
                with self._lock:
                    self._display_reuse.add(inst.display_index)

    def _recycle_idle(self) -> int:
        """回收空闲（无会话引用）且空闲超过 TTL 的实例。返回回收数量。"""
        recycled = 0
        for key, inst in list(self._instances.items()):
            if inst.is_default:
                continue
            if inst.is_idle and inst.idle_seconds is not None and inst.idle_seconds >= self._idle_ttl:
                self._close_instance(key, "空闲超时回收")
                recycled += 1
        return recycled

    # ---- 实例获取 ----
    def _alloc_port(self) -> int:
        port = self._next_port
        self._next_port += 1
        return port

    def _alloc_display(self) -> int:
        """分配独立 Xvfb display 号（复用已释放的号）。"""
        if self._display_reuse:
            return self._display_reuse.pop()
        idx = self._next_display
        self._next_display += 1
        return idx

    def get(
        self, key: Optional[str] = None, fp_env: Optional[Dict[str, str]] = None, chrome_path: Optional[str] = None
    ) -> ChromeInstance:
        """获取（或创建）指定 key 的实例。key=None 表示默认实例。

        chrome_path 指定该实例使用的浏览器二进制（如真实 Google Chrome）。
        不同 chrome_path 视为不同实例（隔离）。
        """
        key = key or DEFAULT_KEY
        # 同一 key 不同二进制 → 加二进制后缀隔离
        if chrome_path and chrome_path != CHROME_PATH:
            key = f"{key}::{os.path.basename(chrome_path)}"
        with self._lock:
            inst = self._instances.get(key)
            if inst is None:
                self._evict_if_needed()
                port = self._alloc_port()
                display_index = self._alloc_display()
                if key.startswith(DEFAULT_KEY):
                    user_dir = os.path.join(USER_DATA_PATH, _sanitize_key(key))
                else:
                    user_dir = os.path.join(PROFILE_DATA_DIR, _sanitize_key(key))
                inst = ChromeInstance(
                    key=key,
                    fp_env=fp_env,
                    user_data_dir=user_dir,
                    port=port,
                    is_default=(key == DEFAULT_KEY),
                    chrome_path=chrome_path,
                    display_index=display_index,
                )
                self._instances[key] = inst
                logger.info(
                    f"[pool] 创建浏览器实例: {key} "
                    f"(port={port}, display=:{display_index}, chrome={chrome_path or CHROME_PATH})"
                )
            return inst

    # 真实 Google Chrome 路径（对 Google 等严格站点使用）
    def get_real_chrome(self) -> ChromeInstance:
        """获取（或创建）使用真实 Google Chrome 的实例。"""
        real_path = "/usr/bin/google-chrome-stable"
        if not os.path.exists(real_path):
            raise RuntimeError("真实 Google Chrome 不存在: " + real_path)
        return self.get("google", chrome_path=real_path)

    def ensure_browser_with_profile(
        self, profile_id: Optional[str], fp_env: Optional[Dict[str, str]] = None
    ) -> tuple[Chromium, str]:
        """按画像 ID 确保浏览器就绪（会话路由入口）。

        Returns:
            (Chromium, instance_key)：浏览器对象 + 实例 key（供会话引用计数回收）。
        """
        key = profile_id or DEFAULT_KEY
        inst = self.get(key, fp_env)
        return inst.ensure(), key

    def ensure_browser_with_env(self, fp_env: Optional[Dict[str, str]] = None) -> Chromium:
        """兼容旧接口：按 env 切换到默认实例（环境变化会复用/重建默认实例）。"""
        inst = self.get(DEFAULT_KEY, fp_env)
        return inst.ensure()

    @property
    def browser(self) -> Chromium:
        """默认实例（旧接口兼容）。"""
        return self.get(DEFAULT_KEY).ensure()

    @property
    def is_alive(self) -> bool:
        inst = self._instances.get(DEFAULT_KEY)
        return bool(inst and inst.is_alive)

    def _evict_if_needed(self) -> None:
        """实例数超限时，回收空闲实例（仅无会话引用的），避免内存耗尽。"""
        if len(self._instances) < self._max_browsers:
            return
        dead = [i for i in self._instances.values() if not i.is_alive]
        if dead:
            # 优先回收已死亡实例
            for i in dead:
                self._instances.pop(i.key, None)
                i.shutdown()
            return
        # 只回收空闲实例（无会话引用），避免关闭正在使用的浏览器
        idle_candidates = sorted(
            (i for i in self._instances.values() if not i.is_default and i.is_idle),
            key=lambda i: i.last_used,
        )
        if idle_candidates:
            victim = idle_candidates[0]
            logger.info(f"[pool] 实例数超限，回收空闲实例: {victim.key}")
            self._instances.pop(victim.key, None)
            victim.shutdown()

    # ---- 监控 / 清理 ----
    async def monitor_all(self) -> None:
        while True:
            await asyncio.sleep(BROWSER_MONITOR_INTERVAL)
            # 回收空闲超时的实例（无会话引用 + 空闲超过 TTL）
            try:
                self._recycle_idle()
            except Exception as e:
                logger.debug(f"[pool] 空闲实例回收异常: {e}")
            for inst in list(self._instances.values()):
                if inst.reap_dead_browser():
                    logger.warning(f"[fp:{inst.key}] 浏览器异常，标记重建")

    async def start_monitoring(self) -> None:
        self._monitor_task = asyncio.create_task(self.monitor_all())

    async def stop_monitoring(self) -> None:
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    def close_all(self) -> None:
        for inst in list(self._instances.values()):
            inst.shutdown()
        self._instances.clear()

    async def cleanup(self) -> None:
        await self.stop_monitoring()
        self.close_all()

    def list_instances(self) -> List[Dict[str, object]]:
        return [
            {
                "key": inst.key,
                "port": inst.port,
                "alive": inst.is_alive,
                "last_used": inst.last_used,
                "ref_count": inst.ref_count,
                "idle_seconds": inst.idle_seconds,
                "display": inst.display,
                "vnc_port": inst.vnc_port,
                "web_port": inst.web_port,
            }
            for inst in self._instances.values()
        ]


def _sanitize_key(key: str) -> str:
    """把 profile_id 转成安全的目录名。"""
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return out[:80] or "profile"


browser_manager = BrowserPool()
