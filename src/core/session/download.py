"""文件下载 mixin — 浏览器原生下载 + JS fetch 二进制回退。"""

import base64
import json
import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from loguru import logger

from src.core.session.fetch import FetchMixin


class DownloadMixin(FetchMixin):
    """使用浏览器网络栈下载文件（自动携带会话 Cookie / UA / 过盾能力）。"""

    def download(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        save_path: Optional[str] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """使用浏览器网络栈下载文件（自动携带会话 Cookie / UA / 过盾能力）。

        优先使用浏览器原生下载（DrissionPage download 管理器）；失败时回退到
        页面内 fetch 取二进制。返回 base64 与文件信息。

        Returns:
            {"url", "content_type", "base64", "size", "saved_path"(可选), "error"(可选)}
        """
        self.touch()
        domain = urlparse(url).netloc
        cookie_header = self.cookie_store.as_header(domain)
        if headers:
            cookie_header = (
                f"{cookie_header}; {headers.get('Cookie', '')}".strip("; ")
                if cookie_header
                else headers.get("Cookie", "")
            )
        # 先导航到同域过盾（如首次访问被 WAF 拦截），再触发下载
        try:
            if domain and (
                self._active_tab_name is None or urlparse(self._get_active_tab().url).netloc != domain  # type: ignore[union-attr]
            ):
                self._browser_fetch_get(url, cookie_header, None, timeout=min(timeout, 30))
        except Exception as e:
            logger.debug(f"[Session:{self.id}] 下载前导航过盾失败(可忽略): {e}")

        tab = self._get_active_tab()
        # 浏览器原生下载：命中挑战时浏览器会自动过盾并落盘（DrissionPage 下载管理器）
        try:
            tab_any: Any = tab
            mission: Any = tab_any._download_by_browser(url, save_path=save_path, timeout=timeout)
            if mission is not None:
                if not hasattr(mission, "wait"):
                    raise RuntimeError(f"下载任务未创建: {mission!r}")
                mission.wait(timeout)
                path = mission.final_path
                if not path:
                    path = getattr(mission, "path", "") or ""
                if path and os.path.exists(path):
                    return self._encode_download_result(url, path)
                raise RuntimeError(f"下载任务未返回文件路径: {path!r}")
            raise RuntimeError("未创建下载任务")
        except Exception as e:
            logger.debug(f"[Session:{self.id}] 浏览器原生下载失败({e})，回退 JS fetch 二进制")
            return self._download_via_js_fetch(url, timeout)

    def _download_via_js_fetch(self, url: str, timeout: int) -> Dict[str, Any]:
        """回退方案：页面内 fetch 取二进制（跨域受限时可能失败）。"""
        tab = self._get_active_tab()
        script = f"""
        async () => {{
            try {{
                const resp = await fetch({json.dumps(url)}, {{credentials: 'include'}});
                const ct = resp.headers.get('content-type') || '';
                const buf = await resp.arrayBuffer();
                let bin = '';
                const bytes = new Uint8Array(buf);
                for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
                return {{status: resp.status, content_type: ct, size: bytes.length,
                        base64: btoa(bin)}};
            }} catch (e) {{ return {{error: String(e)}}; }}
        }}
        """
        try:
            tab_any: Any = tab
            result: Any = tab_any.run_async_js(script, as_expr=False)
        except Exception as e:
            return {"url": url, "error": str(e)}
        if not result:
            return {"url": url, "error": "JS fetch 失败"}
        if result.get("error"):
            return {"url": url, "error": result.get("error")}
        return {
            "url": url,
            "content_type": result.get("content_type"),
            "base64": result.get("base64"),
            "size": result.get("size"),
        }

    @staticmethod
    def _encode_download_result(url: str, path: str) -> Dict[str, Any]:
        """读取已下载文件，编码为 base64 返回（大文件仅返回路径）。"""
        size = os.path.getsize(path)
        MAX_INLINE = 8 * 1024 * 1024  # 8MB 内联返回 base64
        result: Dict[str, Any] = {"url": url, "saved_path": path, "size": size}
        if size <= MAX_INLINE:
            with open(path, "rb") as f:
                result["base64"] = base64.b64encode(f.read()).decode("ascii")
        return result
