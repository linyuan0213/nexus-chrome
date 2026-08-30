"""主FastAPI应用"""

import asyncio
import datetime
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response
from loguru import logger

from src.api.auth import auth_router
from src.api.fp_profiles import fp_router, is_fp_credential
from src.api.routes import sessions_router
from src.config.settings import (
    APP_HOST,
    APP_PORT,
    APP_VERSION,
    CLEANUP_ENABLED,
    CLEANUP_INTERVAL,
    CLEANUP_KEEP_COOKIES,
    CLEANUP_MAX_SIZE_GB,
    SESSION_CLEANUP_INTERVAL,
    USER_DATA_PATH,
)
from src.core.auth import auth_service
from src.core.browser_manager import browser_manager
from src.core.session import subscribe_events, unsubscribe_events
from src.services.session_service import get_session_manager
from src.utils.cleanup import cleanup_user_data_dir, get_directory_size


async def _session_cleanup_loop():
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        try:
            count = await asyncio.to_thread(get_session_manager().delete_expired)
            if count:
                logger.info(f"清理 {count} 个过期会话")
        except Exception as e:
            logger.warning(f"清理过期会话失败: {e}")


async def _profile_cleanup_loop():
    """定期清理 Chrome 用户数据目录，防止 DeferredBrowserMetrics 等目录暴涨。"""
    if not CLEANUP_ENABLED:
        return
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        try:
            result = await asyncio.to_thread(cleanup_user_data_dir, USER_DATA_PATH, CLEANUP_KEEP_COOKIES)
            if result["removed"]:
                logger.info(
                    f"用户数据目录清理完成: 删除 {result['removed']} 项, "
                    f"释放 {result['bytes_freed'] / 1024 / 1024:.2f} MB"
                )
            total_size = await asyncio.to_thread(get_directory_size, Path(USER_DATA_PATH))
            if CLEANUP_MAX_SIZE_GB > 0 and total_size > CLEANUP_MAX_SIZE_GB * 1024**3:
                logger.warning(f"用户数据目录仍超过 {CLEANUP_MAX_SIZE_GB} GB, 执行深度清理")
                deep = await asyncio.to_thread(
                    cleanup_user_data_dir, USER_DATA_PATH, CLEANUP_KEEP_COOKIES, aggressive=True
                )
                logger.info(f"深度清理完成: 删除 {deep['removed']} 项, 释放 {deep['bytes_freed'] / 1024 / 1024:.2f} MB")
        except Exception as e:
            logger.warning(f"用户数据目录清理失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await browser_manager.start_monitoring()
    session_cleanup_task = asyncio.create_task(_session_cleanup_loop())
    profile_cleanup_task = None

    if CLEANUP_ENABLED:
        # 启动前清理一次，避免容器重启后旧数据继承导致暴涨
        try:
            result = await asyncio.to_thread(cleanup_user_data_dir, USER_DATA_PATH, CLEANUP_KEEP_COOKIES)
            if result["removed"]:
                logger.info(
                    f"启动前用户数据清理: 删除 {result['removed']} 项, "
                    f"释放 {result['bytes_freed'] / 1024 / 1024:.2f} MB"
                )
        except Exception as e:
            logger.warning(f"启动前用户数据清理失败: {e}")
        profile_cleanup_task = asyncio.create_task(_profile_cleanup_loop())

    try:
        # 不再预热默认浏览器实例：实例按需创建（会话/指纹出现时才启动 Chrome），
        # 避免容器启动即占用资源
        pass
    except Exception as e:
        logger.warning(f"浏览器预热失败（不影响服务启动）: {e}")
    yield
    session_cleanup_task.cancel()
    try:
        await session_cleanup_task
    except asyncio.CancelledError:
        pass
    if profile_cleanup_task is not None:
        profile_cleanup_task.cancel()
        try:
            await profile_cleanup_task
        except asyncio.CancelledError:
            pass
    await browser_manager.cleanup()


app = FastAPI(
    title="Nexus Chrome Server",
    description="Session 隔离的 Chrome 自动化服务器 — 挑战绕过、Cookie 共享、指纹伪装",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.include_router(sessions_router)
app.include_router(fp_router)
app.include_router(auth_router)


# ---- 认证中间件 ----
# AUTH_PASSWORD 设置时启用：除白名单外的 API/WS 全部要求有效凭证
# （session token 或 scope 匹配的 API Key）。
AUTH_EXEMPT_PREFIXES = (
    "/ui",  # 管理前端静态资源（登录页自身要能打开）
    "/api/auth/config",  # 前端探测是否需要登录
    "/api/auth/login",
    "/chrome",  # noVNC iframe（VNC 密码在 URL 参数中，由 x11vnc 校验）
    "/docs",
    "/openapi.json",
)
AUTH_EXEMPT_EXACT = ("/", "/status")  # 健康检查


def _auth_exempt(path: str) -> bool:
    if path in AUTH_EXEMPT_EXACT:
        return True
    return any(path.startswith(p) for p in AUTH_EXEMPT_PREFIXES)


@app.middleware("http")
async def auth_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if not auth_service.enabled or _auth_exempt(request.url.path):
        return await call_next(request)
    # Header 优先；WebSocket 等无法带头的场景走 query 参数
    token = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.query_params.get("Authorization", "").removeprefix("Bearer ").strip()
    # 画像配置中心的管理/节点凭证（FP_ADMIN_TOKEN/FP_NODE_TOKEN）对 /api/profiles 放行
    if request.url.path.startswith("/api/profiles") and is_fp_credential(token):
        return await call_next(request)
    if not token or not auth_service.verify(token, request.url.path):
        return JSONResponse(status_code=401, content={"detail": "未认证或凭证无效"})
    return await call_next(request)


@app.get("/")
async def root():
    return {
        "message": "Nexus Chrome Server",
        "version": APP_VERSION,
        "docs": "/docs",
        "browser": "ready" if browser_manager.is_alive else "pending",
        "endpoints": {
            "sessions": "POST/GET /sessions",
            "navigate": "POST /sessions/{id}/navigate",
            "html": "GET /sessions/{id}/html",
            "cookies": "GET /sessions/{id}/cookies",
            "click": "POST /sessions/{id}/click",
            "input": "POST /sessions/{id}/input",
            "execute": "POST /sessions/{id}/execute",
            "fetch": "POST /sessions/{id}/fetch",
            "status": "GET /status",
            "fp_profiles": "GET/POST /api/profiles",
            "fp_heartbeat": "GET /api/nodes/{node_id}/heartbeat",
        },
    }


@app.get("/status")
async def status():
    return {
        "status": "running",
        "version": APP_VERSION,
        "browser": "ready" if browser_manager.is_alive else "not_initialized",
        "instances": browser_manager.list_instances(),
        # VNC 密码等敏感配置已移至 /api/auth/me（仅认证后可见）
        "timestamp": datetime.datetime.now().isoformat(),
    }


@app.get("/instances")
async def instances():
    """运行中的指纹 Chrome 实例列表（含每实例 VNC 端口，直连 noVNC 用）。"""
    return {"instances": browser_manager.list_instances()}


@app.delete("/instances/{key}")
async def close_instance(key: str):
    """手动关闭指定浏览器实例（释放内存）。默认实例不可关闭。"""
    if key == "default":
        return {"code": 1, "message": "默认实例不可关闭（可重启服务重建）"}
    try:
        browser_manager.close_instance(key, "手动关闭")
        return {"code": 0, "message": f"实例 {key} 已关闭"}
    except Exception as e:
        return {"code": 1, "message": str(e)}


@app.post("/instances/{key}/restart")
async def restart_instance(key: str):
    """手动拉起已停止的实例（沿用创建时的指纹环境；默认惰性启动，此接口用于管理端主动启动）。"""
    inst = browser_manager.get_existing(key)
    if inst is None:
        return {"code": 1, "message": f"实例 {key} 不存在（创建会话时按需启动）"}
    try:
        await asyncio.to_thread(inst.ensure)
        return {"code": 0, "message": f"实例 {key} 已启动"}
    except Exception as e:
        return {"code": 1, "message": str(e)}


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket, types: str = "*"):
    """WebSocket 事件推送：会话创建/删除等。

    用法: ws://host:port/ws/events  （订阅全部）
          ws://host:port/ws/events?types=session_created,session_deleted

    认证开启时需在 query 中带 Authorization=Bearer <token>。
    """
    # WebSocket 不受 HTTP 中间件保护，需自行校验
    if auth_service.enabled:
        token = websocket.query_params.get("Authorization", "").removeprefix("Bearer ").strip()
        if not token or not auth_service.verify(token, "/ws/events"):
            await websocket.close(code=4401, reason="未认证")
            return

    await websocket.accept()
    event_types = [t.strip() for t in types.split(",") if t.strip()] or ["*"]
    q = await subscribe_events(event_types)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=15.0)
                await websocket.send_json(payload)
            except asyncio.TimeoutError:
                # 心跳保活
                await websocket.send_json({"type": "ping"})
    except Exception as e:
        logger.debug(f"WebSocket 事件推送结束(连接断开): {e}")
    finally:
        unsubscribe_events(q, event_types)
        try:
            await websocket.close()
        except Exception as e:
            logger.debug(f"WebSocket 关闭失败(可忽略): {e}")


def run() -> None:
    """CLI 入口点"""
    uvicorn.run("src.main:app", host=APP_HOST, port=APP_PORT, reload=False)


if __name__ == "__main__":
    run()
