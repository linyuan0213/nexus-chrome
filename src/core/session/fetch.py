"""浏览器网络栈请求 mixin — 复用过盾能力抓取原始响应体。"""

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast
from urllib.parse import urlparse

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger

from src.challenge.resolver import ChallengeOrchestrator
from src.config.settings import CHALLENGE_TIMEOUT
from src.core.session.cookies import CookieMixin

if TYPE_CHECKING:
    from src.core.session.session import Session


class FetchMixin(CookieMixin):
    """使用浏览器网络栈请求 URL（自动过盾、携带会话 Cookie）。"""

    def _create_fetch_tab(
        self,
        url: str,
        cookies: Optional[List[Dict[str, str]]] = None,
        referer: Optional[str] = None,
    ) -> ChromiumTab:
        """创建用于 browser_fetch 的标签页，不自动导航。"""
        tab = self._make_tab()
        tab.set.load_mode.none()  # type: ignore[union-attr]

        self._apply_init_js(tab)

        if self._user_agent:
            tab.set.user_agent(self._user_agent)  # type: ignore[union-attr]
        if cookies:
            tab.set.cookies(cookies)  # type: ignore[union-attr]
        if referer:
            tab.set.headers({"Referer": referer})  # type: ignore[union-attr]

        return tab

    def _browser_fetch_get(
        self,
        url: str,
        cookie: Optional[str],
        headers: Optional[Dict[str, str]],
        timeout: int,
    ) -> Dict[str, Any]:
        """使用浏览器网络栈通过 GET 请求 URL，并获取原始响应体。

        直接复用 navigate 的过盾能力，取回页面 HTML 作为原始响应体。
        """
        nav_result = cast("Session", self).navigate(url, cookie=cookie, timeout=timeout)
        return {
            "url": nav_result.get("url", url),
            "status_code": 200,
            "headers": {},
            "body": nav_result.get("html", ""),
            "challenge": nav_result.get("challenge"),
        }

    def _browser_fetch_js(
        self,
        url: str,
        cookie: Optional[str],
        method: str,
        headers: Optional[Dict[str, str]],
        data: Any,
        timeout: int,
    ) -> Dict[str, Any]:
        """非 GET 请求：先导航到同 origin 过盾，再用浏览器内 fetch 发送请求。"""
        self.touch()
        domain = urlparse(url).netloc
        cookies = self._merge_cookies(domain, cookie)
        tab = self._create_fetch_tab(url, cookies=cookies)
        name = self._auto_tab_name()
        self._tabs[name] = tab
        self._active_tab_name = name

        try:
            tab.get(url)  # type: ignore[union-attr]
            tab.wait(3)

            orchestrator = ChallengeOrchestrator(timeout=timeout)
            challenge_result = orchestrator.resolve(tab)

            headers_json = json.dumps(headers or {})
            body_str = data if isinstance(data, str) else json.dumps(data) if data is not None else ""

            script = f"""
            async () => {{
                try {{
                    const response = await fetch({json.dumps(url)}, {{
                        method: {json.dumps(method)},
                        headers: {headers_json},
                        body: {json.dumps(body_str)},
                        credentials: 'include'
                    }});
                    const text = await response.text();
                    const headers = {{}};
                    response.headers.forEach((value, key) => {{ headers[key] = value; }});
                    return {{
                        status: response.status,
                        headers: headers,
                        body: text,
                        url: response.url
                    }};
                }} catch (e) {{
                    return {{error: e.message}};
                }}
            }}
            """

            try:
                tab_any: Any = tab
                result: Any = tab_any.run_async_js(script, as_expr=False)
            except Exception as e:
                result = {"error": str(e)}

            if not result:
                result = {"error": "JS fetch did not return a result"}

            result_dict = cast(Dict[str, Any], result)

            if "error" in result_dict:
                raise RuntimeError(f"JS fetch failed: {result_dict.get('error')}")

            self._sync_page_cookies(tab, domain)

            return {
                "url": result_dict.get("url", tab.url),
                "status_code": result_dict.get("status", 200),
                "headers": result_dict.get("headers", {}),
                "body": result_dict.get("body", ""),
                "challenge": challenge_result,
            }
        finally:
            try:
                self.close_tab(name)
            except Exception as e:
                logger.debug(f"[Session:{self.id}] 关闭 fetch 标签页 {name} 失败: {e}")

    def browser_fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Any = None,
        cookie: Optional[str] = None,
        timeout: int = CHALLENGE_TIMEOUT,
    ) -> Dict[str, Any]:
        """使用浏览器网络栈请求 URL，自动过盾并返回原始响应体。"""
        domain = urlparse(url).netloc
        cookie_header = self.cookie_store.as_header(domain)
        if cookie:
            cookie_header = f"{cookie_header}; {cookie}" if cookie_header else cookie

        if method.upper() == "GET":
            return self._browser_fetch_get(url, cookie_header, headers, timeout)

        return self._browser_fetch_js(url, cookie_header, method, headers, data, timeout)
