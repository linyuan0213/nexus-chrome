"""Cookie 操作 mixin — CookieStore 读写与 Cookie 头解析/合并。"""

from typing import Any, Dict, List, Optional

from loguru import logger

from src.core.session.base import SessionBase


class CookieMixin(SessionBase):
    """会话 Cookie 存取（双向同步 CookieStore）。"""

    def _store_cookies(self, domain: str, cookies: List[Dict[str, str]]) -> None:
        for c in cookies:
            self.cookie_store.store(
                domain,
                [
                    {
                        "name": c.get("name", ""),
                        "value": c.get("value", ""),
                        "domain": c.get("domain", domain),
                        "path": c.get("path", "/"),
                    }
                ],
            )

    def _sync_page_cookies(self, tab: Any, domain: str) -> None:
        """从页面同步 Cookie 到 CookieStore（tab.cookies 失败时回退 CDP Storage.getCookies）。"""
        try:
            cookies = tab.cookies()
            if cookies:
                self._store_cookies(domain, cookies)
        except Exception:
            try:
                browser_any: Any = self._browser
                result = browser_any._run_cdp("Storage.getCookies")
                self._store_cookies(domain, result.get("cookies", []))
            except Exception:
                logger.debug(f"[Session:{self.id}] CDP 获取 Cookies 失败，跳过")

    @staticmethod
    def _parse_cookie_header(cookie_str: str) -> List[Dict[str, str]]:
        """把 Cookie 头字符串解析为 DrissionPage 可识别的 cookie 列表。"""
        cookies: List[Dict[str, str]] = []
        if not cookie_str:
            return cookies
        for part in cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, value = part.split("=", 1)
            cookies.append({"name": name.strip(), "value": value.strip()})
        return cookies

    def _merge_cookies(
        self,
        domain: str,
        cookie_header: Optional[str],
    ) -> List[Dict[str, str]]:
        """合并 cookie_store 与用户传入的 Cookie。"""
        cookies = self.cookie_store.get(domain)
        for c in cookies:
            c.setdefault("domain", domain)
            c.setdefault("path", "/")
        if cookie_header:
            user_cookies = self._parse_cookie_header(cookie_header)
            existing_names = {c.get("name") for c in cookies}
            for c in user_cookies:
                if c.get("name") not in existing_names:
                    c.setdefault("domain", domain)
                    c.setdefault("path", "/")
                    cookies.append(c)
        return cookies

    def get_cookies(self, domain: Optional[str] = None) -> Dict[str, Any]:
        self.touch()
        if domain:
            return {domain: self.cookie_store.as_dict(domain)}
        return self.cookie_store.as_full_dict()
