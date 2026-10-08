"""会话服务 — 应用层编排：指纹解析 → 浏览器实例路由 → 会话管理。

分层：api → services → {core, fp, challenge, http}
- core 不感知 fp（Session 只持有解析后的 fp_env）
- 本层是唯一同时依赖 core 与 fp 的地方（打破 core↔fp 纠缠）
"""

import os
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from src.config.settings import DATA_DIR
from src.core.browser_manager import BrowserPool, browser_manager
from src.core.session import SessionManager
from src.fp.service import resolve_profile_env
from src.fp.store import store
from src.fp.ua import profile_fits_ua

session_manager: Optional[SessionManager] = None


def _choose_profile_for_ua(user_agent: str) -> Optional[str]:
    """按 UA 的平台 + Chrome 主版本挑选自洽的画像（无匹配返回 None）。

    画像决定补丁 Chromium 的 `navigator.userAgentData` 与 WebGL 渲染栈；会话 UA
    只有与画像平台/主版本一致，Cloudflare 才不会因身份矛盾拒绝 Turnstile。
    """
    try:
        profiles = store.list_profiles()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"读取画像列表失败，跳过 UA 画像匹配: {e}")
        return None
    for prof in profiles:
        if not prof.get("enabled", True):
            continue
        pid = prof.get("profile_id")
        if not pid:
            continue
        try:
            env = resolve_profile_env(pid)
        except Exception:  # noqa: BLE001
            continue
        if env and profile_fits_ua(env, user_agent):
            return pid
    return None


def _reconcile_ua_profile(
    user_agent: Optional[str],
    fp_profile_id: Optional[str],
    fp_env: Optional[Dict[str, str]],
) -> Tuple[Optional[str], Optional[Dict[str, str]], Optional[str]]:
    """让会话 UA 与绑定画像的身份（平台/主版本）保持自洽。

    返回 `(fp_profile_id, fp_env, user_agent)`：
    - UA 与画像一致：原样返回；
    - 冲突且存在匹配画像：改用匹配画像（UA 与 userAgentData/WebGL 自洽）；
    - 冲突且无匹配画像：放弃 UA 覆盖（保留画像原生 UA），避免自相矛盾被 CF 拒绝。
    """
    if not user_agent:
        return fp_profile_id, fp_env, user_agent
    # 指定画像且 env 已解析且与 UA 自洽 → 原样使用（要求 fp_env 非空，否则无法判定）
    if fp_profile_id and fp_env and profile_fits_ua(fp_env, user_agent):
        return fp_profile_id, fp_env, user_agent
    matched = _choose_profile_for_ua(user_agent)
    if matched:
        logger.info(
            f"会话 UA 与画像 {fp_profile_id or '(默认)'} 平台/版本不一致，自动绑定匹配画像 {matched} 以保持指纹自洽"
        )
        return matched, resolve_profile_env(matched), user_agent
    logger.warning(
        f"会话 UA 与指纹画像 {fp_profile_id or '(默认)'} 不一致且无匹配画像，"
        "忽略 UA 覆盖以保持指纹自洽（避免 Cloudflare 身份矛盾）"
    )
    return fp_profile_id, fp_env, None


def get_session_manager(pool: Optional[BrowserPool] = None) -> SessionManager:
    global session_manager
    if session_manager is None:
        session_manager = SessionManager(
            pool or browser_manager,
            persist_file=os.path.join(DATA_DIR, "sessions.json"),
        )
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
    # 记录调用方声明的身份，供响应对比实际生效值（UA 被放弃 / 画像被切换时可见）
    requested_user_agent = user_agent
    requested_fp_profile_id = fp_profile_id
    # 会话 UA 与绑定画像必须平台/主版本自洽，否则补丁 Chromium 的 userAgentData/WebGL
    # 会与 UA 自相矛盾，被 Cloudflare 拒绝（见 src/fp/ua.py）。
    fp_profile_id, fp_env, user_agent = _reconcile_ua_profile(user_agent, fp_profile_id, fp_env)
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
        requested_user_agent=requested_user_agent,
        requested_fp_profile_id=requested_fp_profile_id,
    )
