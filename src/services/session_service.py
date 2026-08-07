"""会话服务 — 应用层编排：指纹解析 → 浏览器实例路由 → 会话管理。

分层：api → services → {core, fp, challenge, http}
- core 不感知 fp（Session 只持有解析后的 fp_env）
- 本层是唯一同时依赖 core 与 fp 的地方（打破 core↔fp 纠缠）
"""

import os
from typing import Any, Dict, Optional

from loguru import logger

from src.core.browser_manager import BrowserPool, browser_manager
from src.core.session import SessionManager
from src.fp.service import resolve_profile_env

session_manager: Optional[SessionManager] = None


def get_session_manager(pool: Optional[BrowserPool] = None) -> SessionManager:
    global session_manager
    if session_manager is None:
        persist_file = None
        try:
            from src.config.settings import DATA_DIR

            persist_file = os.path.join(DATA_DIR, "sessions.json")
        except Exception:  # noqa: BLE001
            persist_file = os.path.join(os.getcwd(), "data", "sessions.json")
        session_manager = SessionManager(pool or browser_manager, persist_file=persist_file)
    return session_manager


def create_session(
    session_id: str,
    fingerprint_profile: str = "stealth",
    user_agent: Optional[str] = None,
    proxy: Optional[str] = None,
    fp_profile_id: Optional[str] = None,
) -> Any:
    """创建会话：解析指纹 env → 路由到对应 Chrome 实例 → 创建 Session。

    - fp_profile_id: 指纹画像（补丁 Chromium，独立实例）
    - use_real_chrome: 使用真实 Google Chrome（对 Google 等严格检测修改二进制的站点）
    core 层不感知 fp 层；fp_env 供 Session 做网络层 UA 头一致性覆盖。
    """
    sm = get_session_manager()
    fp_env: Optional[Dict[str, str]] = None
    if fp_profile_id:
        try:
            fp_env = resolve_profile_env(fp_profile_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Session:{session_id}] 解析指纹画像失败: {e}")
    browser, instance_key = sm.pool.ensure_browser_with_profile(fp_profile_id, fp_env)
    # 关联实例引用（会话删除时无其他引用则回收实例）
    sm.pool.retain(instance_key)
    return sm.create(
        session_id=session_id,
        fingerprint_profile=fingerprint_profile,
        user_agent=user_agent,
        proxy=proxy,
        browser=browser,
        fp_profile_id=fp_profile_id,
        fp_env=fp_env,
        instance_key=instance_key,
    )
