"""指纹服务 — 画像解析、环境渲染、浏览器应用。

接线：会话/站点 → profile_id → 画像 → FP_* 环境变量 → 独立 Chrome 实例。
"""

from typing import Dict, Optional

from loguru import logger

from src.core.browser_manager import browser_manager
from src.fp.render import render_env
from src.fp.sync_client import get_profile


def resolve_profile_env(profile_id: Optional[str]) -> Optional[Dict[str, str]]:
    """按画像 ID 解析 FP_* 环境变量字典；无画像时返回 None（不注入）。"""
    if not profile_id:
        return None
    profile = get_profile(profile_id)
    if profile is None:
        logger.warning(f"画像 {profile_id} 不存在，跳过指纹注入")
        return None
    return render_env(profile.fingerprint, profile_id=profile.profile_id)


def apply_profile_to_browser(profile_id: Optional[str]):
    """确保指定画像的 Chrome 实例就绪（不同画像各自独立实例）。"""
    fp_env = resolve_profile_env(profile_id)
    return browser_manager.ensure_browser_with_profile(profile_id, fp_env)
