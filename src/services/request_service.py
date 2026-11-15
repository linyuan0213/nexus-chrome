"""请求编排服务 — fetch 优先，命中 WAF 挑战时按策略回退。

策略链：
1. return_html：直接 navigate 渲染取 HTML
2. 默认：httpx fetch（快、无浏览器开销）
3. 命中挑战：browser_fetch（浏览器网络栈取原始响应）或 navigate 过盾后再 fetch
"""

import asyncio
from typing import Any, Dict, Optional

from src.config.settings import HTTP_CLIENT_TIMEOUT, HTTP_MAX_REDIRECTS
from src.http.client import HttpClient

_CHALLENGE_STATUS_CODES = {403, 503}
# 只匹配整页 WAF/interstitial 强特征；普通业务 JSON 的 403/429 和页面正文
# 里的 "challenge"/"please wait" 不能直接触发过盾。
_CHALLENGE_INDICATORS = (
    "_cf_chl_opt",
    "cf-browser-verification",
    "cf-im-under-attack",
    "challenge-form",
    "checking your browser",
    "just a moment",
    "ray id",
    "slg-bg",
    "slg-box",
    "ddos protection",
)


def is_challenge_response(result: Dict[str, Any]) -> bool:
    """判断 fetch 结果是否命中整页 WAF/盾。"""
    body = str(result.get("body") or "").lower()
    if not any(indicator in body for indicator in _CHALLENGE_INDICATORS):
        return False
    status = result.get("status_code")
    # 403/503 必须同时有强特征；200 的拦截页也允许命中。
    return status == 200 or status in _CHALLENGE_STATUS_CODES


def clean_response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """移除 body 已解码后不再适用的压缩相关头，避免下游重复解码。"""
    cleaned = dict(headers)
    for key in list(cleaned.keys()):
        if key.lower() in ("content-encoding", "transfer-encoding"):
            cleaned.pop(key)
    return cleaned


async def execute_request(
    session: Any,
    *,
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Any = None,
    cookie: Optional[str] = None,
    navigate_if_challenge: bool = True,
    browser_fetch_on_challenge: bool = True,
    return_html: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """聚合请求：fetch 优先；命中挑战且允许时改用浏览器网络栈或 navigate 过盾后再 fetch。"""
    client = HttpClient(
        base_timeout=HTTP_CLIENT_TIMEOUT,
        max_redirects=HTTP_MAX_REDIRECTS,
        proxy=session.get_proxy() if hasattr(session, "get_proxy") else None,
    )

    if return_html:
        # 渲染模式：直接 navigate 取 HTML
        result = await asyncio.to_thread(session.navigate, url, None, cookie, None, timeout)
        return {
            "status_code": 200,
            "headers": {"content-type": "text/html; charset=utf-8"},
            "body": "",
            "html": result.get("html", ""),
            "challenge": result.get("challenge"),
            "url": result.get("url", url),
        }

    fetch_headers = dict(headers or {})
    if cookie:
        fetch_headers["Cookie"] = cookie

    # HTTP 模式：先 fetch
    result = await asyncio.to_thread(
        client.fetch,
        url=url,
        method=method,
        headers=fetch_headers,
        data=data,
        cookie_store=session.cookie_store,
        timeout=timeout,
    )

    # 命中挑战且允许回退时过盾
    if is_challenge_response(result) and navigate_if_challenge:
        if browser_fetch_on_challenge:
            # 使用浏览器网络栈重新请求，获取原始响应体
            result = await asyncio.to_thread(
                session.browser_fetch,
                url,
                method,
                fetch_headers,
                data,
                cookie,
                timeout,
            )
        else:
            nav_result = await asyncio.to_thread(session.navigate, url, None, cookie, None, timeout)
            # 过盾后再 fetch 一次
            result = await asyncio.to_thread(
                client.fetch,
                url=url,
                method=method,
                headers=fetch_headers,
                data=data,
                cookie_store=session.cookie_store,
                timeout=timeout,
            )
            result["challenge"] = nav_result.get("challenge")
            result["url_after_challenge"] = nav_result.get("url", url)

    result["headers"] = clean_response_headers(result.get("headers", {}))
    return result
