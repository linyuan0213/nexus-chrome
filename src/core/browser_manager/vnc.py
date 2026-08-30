"""实例级 VNC 栈 — x11vnc + websockify（noVNC 网页访问）。"""

import shutil
import subprocess
from typing import ClassVar, Dict, Optional

from loguru import logger

from src.config.settings import VNC_ENABLED, VNC_PASSWORD, VNC_WEB_PORT_MAX


class VncStack:
    """单个浏览器实例的 VNC 进程栈（独立 display → noVNC 网页端口）。"""

    # 端口 → 栈 的全局注册表：同端口新建栈时先停掉旧栈，防止对象被替换后
    # 旧栈的 websockify/x11vnc 无人清理（端口被多个进程 SO_REUSEPORT 共享，
    # noVNC 连接落到死链路上表现为"能看不能点"）。
    _active_by_port: ClassVar[Dict[int, "VncStack"]] = {}

    def __init__(
        self,
        key: str,
        display: Optional[str],
        vnc_port: Optional[int],
        web_port: Optional[int],
    ):
        self._key = key
        self._display = display
        self._vnc_port = vnc_port
        self._web_port = web_port
        self._x11vnc_proc: Optional[subprocess.Popen[bytes]] = None
        self._websockify_proc: Optional[subprocess.Popen[bytes]] = None

    @staticmethod
    def _alive(proc: Optional[subprocess.Popen[bytes]]) -> bool:
        return proc is not None and proc.poll() is None

    def start(self) -> None:
        """启动 x11vnc + websockify（幂等：两个进程都存活才跳过）。"""
        if not VNC_ENABLED or self._vnc_port is None or self._web_port is None or self._display is None:
            return
        if self._web_port > VNC_WEB_PORT_MAX:
            logger.warning(f"[fp:{self._key}] websockify 端口 {self._web_port} 超过上限 {VNC_WEB_PORT_MAX}，跳过 VNC")
            return
        if self._alive(self._x11vnc_proc) and self._alive(self._websockify_proc):
            return
        # 同端口旧栈残留（本实例对象被替换）→ 先停掉
        prev = VncStack._active_by_port.get(self._web_port)
        if prev is not None and prev is not self:
            logger.info(f"[fp:{self._key}] web 端口 {self._web_port} 存在旧 VNC 栈，先清理")
            prev.stop()
        # 部分死亡（如 x11vnc 死了 websockify 还活着）→ 先整体停掉再拉起，避免端口重复占用
        if self._alive(self._x11vnc_proc) or self._alive(self._websockify_proc):
            self.stop()
        try:
            self._x11vnc_proc = subprocess.Popen(
                [
                    "x11vnc",
                    "-display",
                    self._display,
                    "-forever",
                    "-shared",
                    "-passwd",
                    VNC_PASSWORD,
                    "-rfbport",
                    str(self._vnc_port),
                    "-listen",
                    "127.0.0.1",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.debug(f"[fp:{self._key}] 启动 x11vnc 失败: {e}")
        try:
            websockify = shutil.which("websockify") or "/app/.venv/bin/websockify"
            self._websockify_proc = subprocess.Popen(
                [
                    websockify,
                    str(self._web_port),
                    f"127.0.0.1:{self._vnc_port}",
                    "--web",
                    "/opt/noVNC",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.debug(f"[fp:{self._key}] 启动 websockify 失败: {e}")
        VncStack._active_by_port[self._web_port] = self
        logger.info(f"[fp:{self._key}] VNC 就绪: display={self._display} vnc=:{self._vnc_port} web=:{self._web_port}")

    def stop(self) -> None:
        """停止 websockify / x11vnc。"""
        for name, attr in (("websockify", "_websockify_proc"), ("x11vnc", "_x11vnc_proc")):
            proc = getattr(self, attr)
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    logger.debug(f"[fp:{self._key}] 终止 {name} 失败，继续")
                setattr(self, attr, None)
        if self._web_port is not None and VncStack._active_by_port.get(self._web_port) is self:
            del VncStack._active_by_port[self._web_port]
