"""HTTP 客户端 — 基于 httpx2，与 Session 的 CookieStore 双向同步 Cookie。"""

from datetime import timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from time import time
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlparse

import httpx2
from loguru import logger

from src.utils.cookie_header import merge_cookie_header


class HttpClient:
    def __init__(self, base_timeout: int = 30, max_redirects: int = 10, proxy: Optional[str] = None):
        self.base_timeout = base_timeout
        self.max_redirects = max_redirects
        self.proxy = proxy

    def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Any = None,
        cookie_store: Any = None,
        timeout: Optional[int] = None,
        follow_redirects: bool = True,
    ) -> Dict[str, Any]:
        merged_headers = dict(headers or {})

        used_cookies: List[str] = []
        if cookie_store is not None:
            cookie_header = cookie_store.as_header_for_url(url)
            if cookie_header:
                merged_headers["Cookie"] = merge_cookie_header(merged_headers.get("Cookie", ""), cookie_header)
                used_cookies = [item.get("name", "") for item in cookie_store.get_for_url(url)]

        if timeout is None:
            timeout = self.base_timeout

        try:
            with httpx2.Client(
                timeout=timeout,
                follow_redirects=follow_redirects,
                max_redirects=self.max_redirects,
                proxy=self.proxy,
            ) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=merged_headers,
                    content=data if isinstance(data, (str, bytes)) else None,
                    json=cast(Dict[str, Any], data) if isinstance(data, dict) else None,
                )
                self._update_cookie_store(response, url, cookie_store)
                return {
                    "url": str(response.url),
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text,
                    "cookies_used": used_cookies,
                }
        except Exception as e:
            logger.error(f"HTTP 请求失败: {url} - {e}")
            return {
                "url": url,
                "status_code": -1,
                "headers": {},
                "body": "",
                "cookies_used": used_cookies,
                "error": str(e),
            }

    @staticmethod
    def _update_cookie_store(response: httpx2.Response, url: str, cookie_store: Any) -> None:
        """把响应中的 Set-Cookie 写回 CookieStore。"""
        if cookie_store is None:
            return
        set_cookie = response.headers.get("set-cookie")
        if not set_cookie:
            return
        domain = urlparse(url).netloc
        cookie = SimpleCookie()
        cookie.load(set_cookie)
        cookies: List[Dict[str, str]] = []
        now = time()
        for key in cookie.keys():
            morsel = cookie[key]
            item: Dict[str, Any] = {
                "name": morsel.key,
                "value": morsel.value,
                "domain": morsel.get("domain") or domain,
                "path": morsel.get("path") or "/",
            }
            max_age = morsel.get("max-age")
            if max_age is not None:
                try:
                    item["expires"] = now + int(max_age)
                except ValueError:
                    pass
            elif morsel.get("expires"):
                try:
                    item["expires"] = parsedate_to_datetime(morsel["expires"]).replace(tzinfo=timezone.utc).timestamp()
                except (TypeError, ValueError):
                    pass
            if item.get("expires") is not None and float(item["expires"]) <= now:
                cookie_store.delete_cookie(domain, morsel.key, item["path"])
                continue
            cookies.append(item)
        if cookies:
            cookie_store.store(domain, cookies)
            logger.debug(f"HTTP 响应写回 {len(cookies)} 个 Cookie 到 {domain}")
