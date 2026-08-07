"""浏览器池包 — 多指纹并发 Chrome 实例管理。

架构：每个指纹画像（或默认）对应一个独立的 Chrome 进程，拥有：
- 独立的 user-data-dir（cookie/localStorage/缓存完全隔离）
- 独立的调试端口（DrissionPage 独立连接）
- 独立的 FP_* 环境变量（patched Chromium 按进程读取指纹）

模块划分：env（指纹环境）→ process（进程/显示原语）→ instance（单实例）→ pool（实例池）。
"""

from src.core.browser_manager.instance import ChromeInstance
from src.core.browser_manager.pool import BrowserPool, browser_manager
from src.core.browser_manager.process import DEFAULT_KEY

__all__ = [
    "BrowserPool",
    "ChromeInstance",
    "DEFAULT_KEY",
    "browser_manager",
]
