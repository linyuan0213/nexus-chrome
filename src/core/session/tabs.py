"""标签页管理 mixin — 列举/新建/切换/截图。"""

from typing import Any, Dict, Optional

from loguru import logger

from src.core.session.media import MediaMixin


class TabMixin(MediaMixin):
    """会话内标签页的高层管理操作。"""

    def list_tabs(self) -> Dict[str, Any]:
        """列出会话内所有标签页（名称 + URL）。"""
        with self._lock:
            result: Dict[str, Any] = {"active": self._active_tab_name, "tabs": []}
            for name, tab in self._tabs.items():
                try:
                    url = tab.url  # type: ignore[union-attr]
                except Exception:
                    url = ""
                result["tabs"].append({"name": name, "url": url})
            return result

    def create_tab(self, name: Optional[str] = None, url: Optional[str] = None) -> Dict[str, Any]:
        """新建标签页（可选指定名称与 URL）。"""
        tab_name, tab = self._create_tab_handle(name)  # type: ignore[attr-defined]
        if not url:
            return {"name": tab_name, "url": ""}
        tab_lock = self._tab_lock_for(tab_name)
        with tab_lock:
            try:
                self._load_tab(tab, url)  # type: ignore[attr-defined]
            except Exception:
                with self._lock:
                    self._tabs.pop(tab_name, None)
                    self._tab_locks.pop(tab_name, None)
                try:
                    self._close_tab_handle(tab_name, tab)
                except Exception:
                    logger.warning(f"[Session:{self.id}] 清理创建失败的标签页 {tab_name} 也失败")
                raise
            return {"name": tab_name, "url": str(tab.url or "")}

    def switch_tab(self, tab_name: str) -> Dict[str, Any]:
        """切换活动标签页。"""
        with self._lock:
            if tab_name not in self._tabs:
                raise ValueError(f"标签页 '{tab_name}' 未找到")
            self._active_tab_name = tab_name
            return {"active": tab_name, "url": self._tabs[tab_name].url}  # type: ignore[union-attr]

    def screenshot(self, tab_name: Optional[str] = None, full_page: bool = False) -> Dict[str, Any]:
        """对指定（或活动）标签页截图，返回 base64 PNG。

        Args:
            tab_name: 标签页名称，None 使用活动标签页
            full_page: True=整页截图，False=视口截图

        Returns:
            {"tab": 名称, "full_page": bool, "png_base64": "...", "size": N}
        """
        self.touch()
        name, tab = self._lookup_tab(tab_name)  # type: ignore[attr-defined]
        with self._tab_lock_for(name):
            png = tab.get_screenshot(full_page=full_page, as_base64=True)  # type: ignore[union-attr]
            if isinstance(png, str):
                return {
                    "tab": name,
                    "full_page": full_page,
                    "png_base64": png,
                    "size": len(png),
                }
            raise RuntimeError("截图失败：get_screenshot 未返回 base64")
