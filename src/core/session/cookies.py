"""Cookie 操作 mixin — CookieStore 读写与 Cookie 头解析/合并。"""

from typing import Any, Dict, List, Optional, cast

from loguru import logger

from src.core.session.base import SessionBase

_HEADER_COOKIE_LIMIT = 4096
_ESSENTIAL_COOKIE_NAMES = {
    "PHPSESSID",
    "adult",
    "age_verified",
    "cf_clearance",
    "over18",
    "temp_id",
    "__cf_bm",
    "__cfduid",
}


class CookieMixin(SessionBase):
    """会话 Cookie 存取（双向同步 CookieStore）。"""

    def limit_cookie_header(
        self,
        cookies: List[Dict[str, str]],
        max_bytes: int = _HEADER_COOKIE_LIMIT,
    ) -> List[Dict[str, str]]:
        """裁剪过大的 Cookie 头，优先保留过盾/会话必需的 Cookie."""

        def _size(items: List[Dict[str, str]]) -> int:
            return sum(len(str(item.get("name") or "")) + len(str(item.get("value") or "")) + 2 for item in items)

        if not cookies or _size(cookies) <= max_bytes:
            return cookies
        essential = [item for item in cookies if str(item.get("name") or "") in _ESSENTIAL_COOKIE_NAMES]
        selected = list(essential)
        for item in cookies:
            if item in essential:
                continue
            if _size(selected + [item]) <= max_bytes:
                selected.append(item)
        logger.warning(
            f"[Session:{self.id}] Cookie 头超限，已裁剪 "
            f"{len(cookies)} -> {len(selected)} 个，{_size(cookies)} -> {_size(selected)} 字节"
        )
        return selected

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
        page_host = str(domain or "").split(":")[0].lstrip(".").lower()
        if not page_host:
            return

        def _same_site(cookie: Any) -> bool:
            data = cast(Dict[str, Any], cookie) if isinstance(cookie, dict) else {}
            cookie_domain = str(data.get("domain") or page_host).lstrip(".").lower()
            return bool(cookie_domain) and (page_host == cookie_domain or page_host.endswith("." + cookie_domain))

        try:
            cookies = tab.cookies()
            if cookies:
                # tab.cookies() 返回浏览器级全部 Cookie，必须按当前页面域名过滤，
                # 否则搜索站/统计站的大 Cookie 会被错误归到当前站点并撑爆请求头。
                self._store_cookies(domain, [c for c in cookies if _same_site(c)])
        except Exception:
            try:
                browser_any: Any = self._browser
                result = browser_any._run_cdp("Storage.getCookies")
                cookies = result.get("cookies", [])
                self._store_cookies(domain, [c for c in cookies if _same_site(c)])
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

    def delete_cookie(self, domain: str, name: str) -> bool:
        """删除单个 Cookie（镜像存储级，供管理端操作）。"""
        self.touch()
        return self.cookie_store.delete_cookie(domain, name)
