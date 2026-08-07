"""API 路由 — Session 为操作单元。"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.schemas import (
    ApiResponse,
    ClickRequest,
    CreateSessionRequest,
    CreateTabRequest,
    DownloadRequest,
    DragRequest,
    ExecuteRequest,
    HttpFetchRequest,
    InputRequest,
    M3u8Request,
    NavigateRequest,
    RequestOperation,
    ScreenshotRequest,
    SetProxyRequest,
    SwitchTabRequest,
)
from src.config.settings import HTTP_CLIENT_TIMEOUT, HTTP_MAX_REDIRECTS
from src.http.client import HttpClient
from src.services.session_service import create_session, get_session_manager

sessions_router = APIRouter(prefix="/sessions", tags=["sessions"])

# 兼容占位：服务层维护全局 SessionManager（测试 mock 目标）
session_manager = None


def _get_sm():
    """获取全局 SessionManager（服务层单例）。"""
    return get_session_manager()


@sessions_router.post("", response_model=ApiResponse)
async def create_session_route(request: CreateSessionRequest):
    try:
        session = await asyncio.to_thread(
            create_session,
            request.session_id,
            request.fingerprint_profile,
            request.user_agent,
            request.proxy,
            request.fp_profile_id,
        )
        return ApiResponse(code=0, message="会话已创建", data=session.to_dict())
    except ValueError as e:
        # 已存在则直接返回现有会话
        if "已存在" in str(e):
            session = _get_sm().get(request.session_id)
            return ApiResponse(code=0, message="会话已存在", data=session.to_dict())
        raise HTTPException(status_code=409, detail=str(e))


@sessions_router.get("", response_model=ApiResponse)
async def list_sessions():
    sm = _get_sm()
    recovered = sm.recovered_sessions()
    return ApiResponse(
        code=0,
        message="ok",
        data={"sessions": sm.list_all(), "recovered": recovered},
    )


@sessions_router.delete("/{session_id}", response_model=ApiResponse)
async def delete_session(session_id: str):
    try:
        sm = _get_sm()
        await asyncio.to_thread(sm.delete, session_id)
        return ApiResponse(code=0, message=f"会话 {session_id} 已删除", data=None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@sessions_router.post("/{session_id}/navigate", response_model=ApiResponse)
async def navigate(session_id: str, request: NavigateRequest):
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(
            session.navigate,
            request.url,
            request.tab_name,
            request.cookie,
            request.referer,
            request.timeout,
        )
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sessions_router.get("/{session_id}/html", response_model=ApiResponse)
async def get_html(session_id: str):
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.get_html)
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@sessions_router.get("/{session_id}/cookies", response_model=ApiResponse)
async def get_cookies(session_id: str, domain: str = Query(None)):
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = session.get_cookies(domain)
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@sessions_router.post("/{session_id}/click", response_model=ApiResponse)
async def click(session_id: str, request: ClickRequest):
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        await asyncio.to_thread(session.click, request.selector, request.humanize)
        return ApiResponse(code=0, message=f"已点击: {request.selector}", data=None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sessions_router.post("/{session_id}/drag", response_model=ApiResponse)
async def drag(session_id: str, request: DragRequest):
    """人性化拖拽（滑块验证码）：按弧线轨迹移动，对抗轨迹检测。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        await asyncio.to_thread(session.drag, request.selector, request.offset_x, request.offset_y, request.duration)
        return ApiResponse(
            code=0, message=f"已拖拽: {request.selector} (+{request.offset_x},{request.offset_y})", data=None
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sessions_router.post("/{session_id}/input", response_model=ApiResponse)
async def input_text(session_id: str, request: InputRequest):
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        await asyncio.to_thread(session.input_text, request.selector, request.text)
        return ApiResponse(code=0, message=f"已输入: {request.text}", data=None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sessions_router.post("/{session_id}/execute", response_model=ApiResponse)
async def execute_js(session_id: str, request: ExecuteRequest):
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.execute, request.script)
        return ApiResponse(code=0, message="ok", data={"result": result})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sessions_router.post("/{session_id}/fetch", response_model=ApiResponse)
async def http_fetch(session_id: str, request: HttpFetchRequest):
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        client = HttpClient(
            base_timeout=HTTP_CLIENT_TIMEOUT,
            max_redirects=HTTP_MAX_REDIRECTS,
        )
        result = await asyncio.to_thread(
            client.fetch,
            url=request.url,
            method=request.method,
            headers=request.headers,
            data=request.data,
            cookie_store=session.cookie_store,
            timeout=request.timeout,
        )
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_CHALLENGE_STATUS_CODES = {403, 503, 429}
_CHALLENGE_INDICATORS = [
    "Just a moment",
    "cf-turnstile-response",
    "Checking your browser",
    "DDoS protection",
    "challenge",
    "cf-challenge",
    "please wait",
]


def _is_challenge_response(result: dict[str, Any]) -> bool:
    """判断 fetch 结果是否命中 WAF/盾。"""
    if result.get("status_code") in _CHALLENGE_STATUS_CODES:
        return True
    body = (result.get("body") or "").lower()
    return any(indicator.lower() in body for indicator in _CHALLENGE_INDICATORS)


def _clean_response_headers(headers: dict[str, str]) -> dict[str, str]:
    """移除 body 已解码后不再适用的压缩相关头，避免下游重复解码。"""
    cleaned = dict(headers)
    for key in list(cleaned.keys()):
        if key.lower() in ("content-encoding", "transfer-encoding"):
            cleaned.pop(key)
    return cleaned


@sessions_router.post("/{session_id}/request", response_model=ApiResponse)
async def unified_request(session_id: str, request: RequestOperation):
    """聚合请求：fetch 优先；命中挑战且允许时改用浏览器网络栈或 navigate 过盾后再 fetch。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        client = HttpClient(
            base_timeout=HTTP_CLIENT_TIMEOUT,
            max_redirects=HTTP_MAX_REDIRECTS,
        )

        if request.return_html:
            # 渲染模式：直接 navigate 取 HTML
            result = await asyncio.to_thread(
                session.navigate,
                request.url,
                None,
                request.cookie,
                None,
                request.timeout,
            )
            return ApiResponse(
                code=0,
                message="ok",
                data={
                    "status_code": 200,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": "",
                    "html": result.get("html", ""),
                    "challenge": result.get("challenge"),
                    "url": result.get("url", request.url),
                },
            )

        fetch_headers = dict(request.headers or {})
        if request.cookie:
            fetch_headers["Cookie"] = request.cookie

        # HTTP 模式：先 fetch
        result = await asyncio.to_thread(
            client.fetch,
            url=request.url,
            method=request.method,
            headers=fetch_headers,
            data=request.data,
            cookie_store=session.cookie_store,
            timeout=request.timeout,
        )

        # 命中挑战且允许回退时过盾
        if _is_challenge_response(result) and request.navigate_if_challenge:
            if request.browser_fetch_on_challenge:
                # 使用浏览器网络栈重新请求，获取原始响应体
                result = await asyncio.to_thread(
                    session.browser_fetch,
                    request.url,
                    request.method,
                    fetch_headers,
                    request.data,
                    request.cookie,
                    request.timeout,
                )
            else:
                nav_result = await asyncio.to_thread(
                    session.navigate,
                    request.url,
                    None,
                    request.cookie,
                    None,
                    request.timeout,
                )
                # 过盾后再 fetch 一次
                result = await asyncio.to_thread(
                    client.fetch,
                    url=request.url,
                    method=request.method,
                    headers=fetch_headers,
                    data=request.data,
                    cookie_store=session.cookie_store,
                    timeout=request.timeout,
                )
                result["challenge"] = nav_result.get("challenge")
                result["url_after_challenge"] = nav_result.get("url", request.url)

        result["headers"] = _clean_response_headers(result.get("headers", {}))
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- P1 媒体场景能力 ----------


@sessions_router.get("/{session_id}/tabs", response_model=ApiResponse)
async def list_tabs(session_id: str):
    """列出会话内所有标签页。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.list_tabs)
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@sessions_router.post("/{session_id}/tabs", response_model=ApiResponse)
async def create_tab(session_id: str, request: CreateTabRequest):
    """新建标签页（可选名称与初始 URL）。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.create_tab, request.name, request.url)
        return ApiResponse(code=0, message="标签页已创建", data=result)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@sessions_router.post("/{session_id}/tabs/switch", response_model=ApiResponse)
async def switch_tab(session_id: str, request: SwitchTabRequest):
    """切换活动标签页。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.switch_tab, request.name)
        return ApiResponse(code=0, message="已切换", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@sessions_router.delete("/{session_id}/tabs/{tab_name}", response_model=ApiResponse)
async def close_tab(session_id: str, tab_name: str):
    """关闭指定标签页。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        await asyncio.to_thread(session.close_tab, tab_name)
        return ApiResponse(code=0, message=f"标签页 {tab_name} 已关闭", data=None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@sessions_router.post("/{session_id}/screenshot", response_model=ApiResponse)
async def screenshot(session_id: str, request: ScreenshotRequest):
    """截图（base64 PNG）。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.screenshot, request.tab_name, request.full_page)
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sessions_router.post("/{session_id}/download", response_model=ApiResponse)
async def download(session_id: str, request: DownloadRequest):
    """浏览器下载文件（自动携带 Cookie / 过盾），返回 base64。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.download, request.url, None, request.save_path, request.timeout)
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@sessions_router.post("/{session_id}/m3u8", response_model=ApiResponse)
async def detect_m3u8(session_id: str, request: M3u8Request):
    """抓取并解析 m3u8 播放列表（主列表/媒体列表）。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.detect_m3u8, request.url, request.timeout)
        return ApiResponse(code=0, message="ok", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- P2 会话与网络能力 ----------


@sessions_router.post("/{session_id}/proxy", response_model=ApiResponse)
async def set_proxy(session_id: str, request: SetProxyRequest):
    """运行时切换会话代理。"""
    try:
        sm = _get_sm()
        session = sm.get(session_id)
        result = await asyncio.to_thread(session.set_proxy, request.proxy)
        return ApiResponse(code=0, message="代理已切换", data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
