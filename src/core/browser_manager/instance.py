"""ChromeInstance — 单个指纹的 Chrome 实例（进程 + 存储 + 指纹 env 隔离）。"""

import os
import subprocess
import threading
import time as _time
from typing import IO, Dict, Optional

from DrissionPage import Chromium, ChromiumOptions
from loguru import logger

from src.config.settings import (
    CHROME_PATH,
    DEFAULT_FINGERPRINT_PROFILE,
    REMOTE_CHROME_ADDRESS,
    VNC_PORT_BASE,
    VNC_WEB_PORT_BASE,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from src.core.browser_manager.env import base_fp_env
from src.core.browser_manager.process import (
    XVFB_DISPLAY,
    build_chrome_args,
    start_xvfb,
    wait_for_port,
)
from src.core.browser_manager.vnc import VncStack


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
        self._vnc = VncStack(key, self.display, self.vnc_port, self.web_port)
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
            self._xvfb_proc = start_xvfb(self.display, self.screen_size)
        else:
            start_xvfb(XVFB_DISPLAY)
        chrome = self.chrome_path or CHROME_PATH or "/opt/google/chrome/google-chrome"
        env = os.environ.copy()
        env.update(base_fp_env())
        env["DISPLAY"] = self.display if self.display is not None else XVFB_DISPLAY
        env.update(self.fp_env)  # 画像环境覆盖基础值（FP_SCREEN_* 按画像）
        # 屏幕尺寸与画像保持一致：Xvfb 按画像尺寸，env 的 FP_SCREEN_* 也同步
        sw, sh = self.screen_size
        env["FP_SCREEN_WIDTH"] = str(sw)
        env["FP_SCREEN_HEIGHT"] = str(sh)
        # 清理残留的 Chrome 配置锁（崩溃/强杀后 SingletonLock 残留会导致拒绝启动）。
        # SingletonLock/SingletonSocket 是符号链接且指向旧容器的失效路径，
        # os.path.exists 对坏链接返回 False，必须用 lexists 才能删掉。
        try:
            for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                lock_path = os.path.join(self.user_data_dir, lock_name)
                if os.path.lexists(lock_path):
                    os.remove(lock_path)
        except Exception:
            logger.debug(f"[fp:{self.key}] 清理 Chrome 配置锁失败，继续")
        args = [
            chrome,
            *build_chrome_args(
                DEFAULT_FINGERPRINT_PROFILE,
                self.user_data_dir,
                self.port,
                self.screen_size,
                # 语言与画像的 FP_LANGS 一致（Accept-Language 头 ↔ navigator.languages）
                languages=env.get("FP_LANGS"),
            ),
        ]
        # 指纹配置以命令行开关传递（--fp-env-<NAME>=value）：
        # Chrome 会过滤渲染/GPU 子进程的环境变量，而开关会透传给所有子进程，
        # 保证 WebGL caps 等需要在渲染进程读取 FP_* 的补丁可靠生效。
        # 只传无空格的 WebGL 参数开关（UA/renderer 等含空格的值走 CDP/其他通道，
        # 否则空格会被子进程命令行解析拆开导致崩溃）。
        # 开关名必须全小写（Chromium IsSwitchNameValid: ToLowerASCII==self）。
        # FP_BATTERY_* 数值型无空格，也走开关：设备服务子进程的 env 可能被过滤，
        # 开关会原样透传（1025-battery-status.patch 在设备服务读取）。
        for key in (
            "FP_WEBGL_PARAMS",
            "FP_WEBGL_VIEWPORT_DIMS",
            "FP_WEBGL_EXTENSIONS_REMOVE",
            "FP_BATTERY_LEVEL",
            "FP_BATTERY_CHARGING",
        ):
            value = self.fp_env.get(key)
            if value:
                args.append(f"--fp-env-{key.lower()}={value}")
        args.append("about:blank")
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
        if not wait_for_port(self.port, timeout=30):
            logger.warning(f"[fp:{self.key}] Chrome 调试端口未在 30 秒内就绪")
        _time.sleep(1)
        self._start_vnc()

    def _start_vnc(self) -> None:
        """为该实例启动 x11vnc + websockify（独立 display → noVNC 网页端口）。"""
        self._vnc.start()

    def _stop_vnc(self) -> None:
        """停止该实例的 websockify / x11vnc（供重启与关闭时复用）。"""
        self._vnc.stop()

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
