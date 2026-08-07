"""标签页管理 mixin — 列举/新建/切换/截图。"""

from typing import Any, Dict, Optional

from src.core.session.media import MediaMixin


class TabMixin(MediaMixin):
    """会话内标签页的高层管理操作。"""

    def list_tabs(self) -> Dict[str, Any]:
        """列出会话内所有标签页（名称 + URL）。"""
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
        tab = self._make_tab()
        tab.set.load_mode.none()  # type: ignore[union-attr]
        self._apply_init_js(tab)
        self._apply_ua_metadata(tab)  # type: ignore[union-attr]
        if self._user_agent:
            tab.set.user_agent(self._user_agent)  # type: ignore[union-attr]
        tab_name = name or self._auto_tab_name()
        if tab_name in self._tabs:
            tab.close()  # type: ignore[union-attr]
            raise ValueError(f"标签页 '{tab_name}' 已存在")
        self._tabs[tab_name] = tab
        self._active_tab_name = tab_name
        if url:
            tab.get(url)  # type: ignore[union-attr]
        return {"name": tab_name, "url": tab.url if url else ""}

    def switch_tab(self, tab_name: str) -> Dict[str, Any]:
        """切换活动标签页。"""
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
        if tab_name:
            if tab_name not in self._tabs:
                raise ValueError(f"标签页 '{tab_name}' 未找到")
            tab = self._tabs[tab_name]
        else:
            tab = self._get_active_tab()
        png = tab.get_screenshot(full_page=full_page, as_base64=True)  # type: ignore[union-attr]
        if isinstance(png, str):
            return {
                "tab": tab_name or self._active_tab_name,
                "full_page": full_page,
                "png_base64": png,
                "size": len(png),
            }
        raise RuntimeError("截图失败：get_screenshot 未返回 base64")
