"""主FastAPI应用"""

import asyncio
import datetime
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from loguru import logger

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
from src.core.browser_manager import browser_manager
from src.core.session import session_manager
from src.utils.cleanup import cleanup_user_data_dir, get_directory_size


async def _session_cleanup_loop():
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        if session_manager is not None:
            try:
                count = await asyncio.to_thread(session_manager.delete_expired)
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
            result = await asyncio.to_thread(
                cleanup_user_data_dir, USER_DATA_PATH, CLEANUP_KEEP_COOKIES
            )
            if result["removed"]:
                logger.info(
                    f"用户数据目录清理完成: 删除 {result['removed']} 项, "
                    f"释放 {result['bytes_freed'] / 1024 / 1024:.2f} MB"
                )
            total_size = await asyncio.to_thread(get_directory_size, Path(USER_DATA_PATH))
            if CLEANUP_MAX_SIZE_GB > 0 and total_size > CLEANUP_MAX_SIZE_GB * 1024**3:
                logger.warning(
                    f"用户数据目录仍超过 {CLEANUP_MAX_SIZE_GB} GB, 执行深度清理"
                )
                deep = await asyncio.to_thread(
                    cleanup_user_data_dir, USER_DATA_PATH, CLEANUP_KEEP_COOKIES, aggressive=True
                )
                logger.info(
                    f"深度清理完成: 删除 {deep['removed']} 项, "
                    f"释放 {deep['bytes_freed'] / 1024 / 1024:.2f} MB"
                )
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
            result = await asyncio.to_thread(
                cleanup_user_data_dir, USER_DATA_PATH, CLEANUP_KEEP_COOKIES
            )
            if result["removed"]:
                logger.info(
                    f"启动前用户数据清理: 删除 {result['removed']} 项, "
                    f"释放 {result['bytes_freed'] / 1024 / 1024:.2f} MB"
                )
        except Exception as e:
            logger.warning(f"启动前用户数据清理失败: {e}")
        profile_cleanup_task = asyncio.create_task(_profile_cleanup_loop())

    try:
        # 触发浏览器预热，失败不影响服务启动
        _ = browser_manager.browser
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
        },
    }


@app.get("/status")
async def status():
    return {
        "status": "running",
        "version": APP_VERSION,
        "browser": "ready" if browser_manager.is_alive else "not_initialized",
        "timestamp": datetime.datetime.now().isoformat(),
    }


def run() -> None:
    """CLI 入口点"""
    uvicorn.run("src.main:app", host=APP_HOST, port=APP_PORT, reload=False)


if __name__ == "__main__":
    run()
