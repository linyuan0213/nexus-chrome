"""BrowserPool — 多指纹 Chrome 实例池：按 key 管理实例生命周期。"""

import asyncio
import os
import threading
from typing import Dict, List, Optional

from DrissionPage import Chromium
from loguru import logger

from src.config.settings import (
    BROWSER_MONITOR_INTERVAL,
    CHROME_PATH,
    MAX_BROWSERS,
    PROFILE_DATA_DIR,
    USER_DATA_PATH,
    VNC_DISPLAY_BASE,
)
from src.core.browser_manager.instance import ChromeInstance
from src.core.browser_manager.process import DEBUG_PORT, DEFAULT_KEY, sanitize_key


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
    def get_existing(self, key: str) -> Optional["ChromeInstance"]:
        """按 key 获取已存在实例（不创建）；不存在返回 None。"""
        with self._lock:
            return self._instances.get(key)

    def retain(self, key: str) -> None:
        """会话创建时关联实例（引用 +1）。"""
        inst = self._instances.get(key)
        if inst is not None:
            inst.retain()

    def release(self, key: str) -> None:
        """会话删除时释放实例（引用 -1）。

        引用归零后不立即关闭实例：保留空闲实例供短时间内的会话复用
        （避免频繁创建/销毁 Chrome 进程的开销），空闲超过 TTL 后由
        _recycle_idle 回收；实例池满时由 _evict_if_needed 驱逐空闲实例。
        """
        inst = self._instances.get(key)
        if inst is None:
            return
        inst.release()

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
                    user_dir = os.path.join(USER_DATA_PATH, sanitize_key(key))
                else:
                    user_dir = os.path.join(PROFILE_DATA_DIR, sanitize_key(key))
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


browser_manager = BrowserPool()
