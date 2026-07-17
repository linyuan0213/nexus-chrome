"""Chrome 用户数据目录清理工具。

用于定期删除 Chrome 在使用过程中产生的缓存、metrics 和其他可丢弃文件，
防止 `DeferredBrowserMetrics` 等目录无限增长。
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Iterable, Optional

from loguru import logger

# 可安全删除的缓存/临时目录与文件（相对于 Chrome user-data-dir 根目录）
DEFAULT_PROFILE_CACHE_ITEMS = (
    "Cookies",
    "Cookies-journal",
    "DeferredBrowserMetrics",
    "BrowserMetrics",
    "Cache",
    "Code Cache",
    "GPUCache",
    "blob_storage",
    "IndexedDB",
    "Local Storage",
    "Session Storage",
    "Service Worker",
    "WebStorage",
    "Platform Notifications",
    "webrtc_event_logs",
    "optimization_guide",
    "Crashpad",
    "DIPS",
    "DIPS-journal",
    "Network Persistent State",
    "chrome_debug.log",
    "chrome_shutdown_ms.txt",
    "DownloadedShutdown",
)

# 当目录大小超过阈值时额外清理的“激进”项
AGGRESSIVE_CACHE_ITEMS = (
    "Safe Browsing",
    "Trust Tokens",
    "Subresource Filter",
    "Default/Storage",
)


def _is_older_than(path: Path, max_age_seconds: int) -> bool:
    """判断文件或目录的修改时间是否超过指定秒数。"""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    return (time.time() - mtime) > max_age_seconds


def get_directory_size(path: Path) -> int:
    """计算目录总字节数。"""
    total = 0
    if not path.exists():
        return 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            try:
                total += file_path.lstat().st_size
            except OSError:
                continue
    return total


def cleanup_user_data_dir(
    user_data_path: Path | str,
    keep_cookies: bool = True,
    max_age_seconds: Optional[int] = None,
    aggressive: bool = False,
    extra_items: Optional[Iterable[str]] = None,
) -> dict[str, int]:
    """清理 Chrome 用户数据目录中的缓存与 metrics 文件。

    Args:
        user_data_path: Chrome `--user-data-dir` 路径。
        keep_cookies: 为 True 时保留 `Cookies` 与 `Cookies-journal`。
        max_age_seconds: 仅删除超过该秒数的文件/目录；0 或 None 表示不限制。
        aggressive: 为 True 时额外清理可能包含站点数据的目录。
        extra_items: 额外的相对路径名称列表。

    Returns:
        {"removed": 删除项数, "bytes_freed": 释放字节数}
    """
    root = Path(user_data_path)
    removed = 0
    bytes_freed = 0
    if not root.exists():
        return {"removed": removed, "bytes_freed": bytes_freed}

    items: list[str] = list(DEFAULT_PROFILE_CACHE_ITEMS)
    if aggressive:
        items.extend(AGGRESSIVE_CACHE_ITEMS)
    if extra_items:
        items.extend(extra_items)

    for name in items:
        # 同时处理 user-data-dir 根目录和 Default 子目录
        targets = [root / name]
        default_dir = root / "Default"
        if default_dir.exists():
            targets.append(default_dir / name)

        for target in targets:
            if not target.exists():
                continue
            if keep_cookies and target.name in {"Cookies", "Cookies-journal"}:
                continue
            if max_age_seconds and not _is_older_than(target, max_age_seconds):
                continue
            try:
                size = get_directory_size(target) if target.is_dir() else target.stat().st_size
            except OSError:
                logger.debug(f"无法计算大小，跳过: {target}")
                continue
            try:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink()
                removed += 1
                bytes_freed += size
                logger.debug(f"已清理: {target} ({size} bytes)")
            except OSError as e:
                logger.warning(f"清理 {target} 失败: {e}")

    return {"removed": removed, "bytes_freed": bytes_freed}
