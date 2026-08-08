"""指纹画像获取 — 本地 store（主）或远程配置中心（多节点可选）。

指纹画像现内建于 nexus-chrome（/api/profiles），本模块负责：
- 单节点：直接读本地 SQLite store（无网络）
- 多节点：从主节点的 /api/profiles 拉取（带 HMAC 验签），写本地缓存
"""

import hashlib
import hmac
import json
import os
import time
from typing import Dict, Optional, Tuple

import httpx2
from loguru import logger

from src.fp.config import FP_CENTER_TOKEN, FP_CENTER_URL
from src.fp.profile import FpProfile
from src.fp.store import store

_CACHE: Dict[str, Tuple[FpProfile, float]] = {}


def get_profile_local(profile_id: str) -> Optional[FpProfile]:
    """从本地 SQLite store 读取画像。"""
    row = store.get_profile(profile_id)
    if not row:
        return None
    return FpProfile(
        profile_id=row["profile_id"],
        name=row["name"],
        version=row["version"],
        enabled=row["enabled"],
        rollout=row["rollout"],
        fingerprint=row["fingerprint"],
    )


def fetch_profile_remote(profile_id: str) -> Optional[FpProfile]:
    """从主节点配置中心拉取画像（多节点场景），验签后返回。"""
    if not FP_CENTER_URL:
        return None
    try:
        headers = {"Authorization": f"Bearer {FP_CENTER_TOKEN}"} if FP_CENTER_TOKEN else {}
        resp = httpx2.get(f"{FP_CENTER_URL}/api/profiles/{profile_id}", headers=headers, timeout=10)
        resp.raise_for_status()
        payload = resp.json().get("data", {})
        data = payload.get("data", {})
        signature = payload.get("signature", "")
        version = payload.get("version", 0)
        # 验签：中心与节点共享 FP_CENTER_SECRET
        secret = os.getenv("FP_CENTER_SECRET", "")
        if secret and not _verify(data, version, signature, secret):
            logger.warning(f"画像 {profile_id} 签名校验失败，拒绝使用")
            return None
        return FpProfile(profile_id=profile_id, version=version, fingerprint=data)
    except Exception as e:
        logger.warning(f"远程拉取画像失败: {e}")
        return None


def get_profile(profile_id: str, use_cache: bool = True, ttl: int = 300) -> Optional[FpProfile]:
    """获取画像：本地 store 优先，缺失时回退远程拉取并写回本地。"""
    now = time.time()
    cached = _CACHE.get(profile_id)
    if use_cache and cached and now - cached[1] < ttl:
        return cached[0]

    profile = get_profile_local(profile_id)
    if profile is None:
        profile = fetch_profile_remote(profile_id)
        if profile is not None:
            # 写回本地 store 供后续使用
            try:
                store.create_or_update(profile.model_dump())
            except Exception as e:
                logger.debug(f"远程画像写回本地失败: {e}")
    if profile is not None:
        _CACHE[profile_id] = (profile, now)
    return profile


def invalidate_cache(profile_id: Optional[str] = None) -> None:
    """使画像内存缓存失效。profile_id=None 时清空全部。

    画像更新/回滚/灰度变更后必须调用，否则 TTL（300s）内新会话仍拿到旧 env。
    """
    if profile_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(profile_id, None)


def _verify(data: Dict[str, object], version: int, signature: str, secret: str) -> bool:
    if not signature:
        return False
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    message = f"{canonical}|{version}"
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
