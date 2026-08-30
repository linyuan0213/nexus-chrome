"""指纹配置中心路由 — 画像 CRUD、灰度/回滚、签名下发、节点心跳。

内建于 nexus-chrome API（见 docs/fp_config_center_api.md）。
鉴权：若设置了 FP_ADMIN_TOKEN / FP_NODE_TOKEN 环境变量则强制校验，
否则开放（默认内网使用）。
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.api.schemas import ApiResponse
from src.core.auth import auth_service
from src.fp.profile import FpProfile, RolloutRule
from src.fp.signing import sign_payload
from src.fp.store import store
from src.fp.sync_client import invalidate_cache

fp_router = APIRouter(prefix="/api", tags=["fingerprint"])

_FP_ADMIN_TOKEN: Optional[str] = os.getenv("FP_ADMIN_TOKEN") or None
_FP_NODE_TOKEN: Optional[str] = os.getenv("FP_NODE_TOKEN") or None


def is_fp_credential(token: str) -> bool:
    """是否为指纹配置中心的管理/节点凭证（供全局认证中间件放行兼容）。"""
    return bool(token) and token in {t for t in (_FP_ADMIN_TOKEN, _FP_NODE_TOKEN) if t}


def _check_token(authorization: Optional[str], required: Optional[str]) -> None:
    # 统一认证开启时：session token / scope=profiles 的 API Key 均放行
    if auth_service.enabled and authorization:
        token = authorization.removeprefix("Bearer ").strip()
        if auth_service.verify(token, "/api/profiles"):
            return
    if not required:
        return  # 未配置 token 则开放
    if not authorization or authorization != f"Bearer {required}":
        raise HTTPException(status_code=401, detail="invalid token")


def require_admin(
    authorization: Optional[str] = Header(default=None),
    auth_query: Optional[str] = Query(default=None, alias="Authorization", include_in_schema=False),
):
    _check_token(authorization or auth_query, _FP_ADMIN_TOKEN)


def require_node(
    authorization: Optional[str] = Header(default=None),
    auth_query: Optional[str] = Query(default=None, alias="Authorization", include_in_schema=False),
):
    _check_token(authorization or auth_query, _FP_NODE_TOKEN)


@fp_router.get("/profiles", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def list_profiles():
    """画像列表。"""
    return ApiResponse(code=0, message="ok", data={"profiles": store.list_profiles()})


@fp_router.get("/profiles/{profile_id}", response_model=ApiResponse, dependencies=[Depends(require_node)])
async def get_profile(profile_id: str):
    """拉取最新画像（节点），响应带 HMAC 签名。"""
    profile = store.get_profile(profile_id)
    if not profile or not profile["enabled"]:
        raise HTTPException(status_code=404, detail="profile not found or disabled")
    return ApiResponse(
        code=0,
        message="ok",
        data={
            "profile_id": profile_id,
            "version": profile["version"],
            "data": profile["fingerprint"],
            "signature": sign_payload(profile["fingerprint"], profile["version"]),
            "issued_at": profile["updated_at"],
        },
    )


@fp_router.get("/profiles/{profile_id}/versions", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def get_versions(profile_id: str):
    """画像历史版本。"""
    rows = store.get_versions(profile_id)
    if not rows:
        raise HTTPException(status_code=404, detail="profile not found")
    return ApiResponse(
        code=0,
        message="ok",
        data={
            "profile_id": profile_id,
            "current_version": rows[0]["version"],
            "versions": rows,
        },
    )


@fp_router.post("/profiles", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def create_or_update(body: FpProfile):
    """创建 / 更新画像，version 自动 +1。"""
    result = store.create_or_update(body.model_dump())
    invalidate_cache(body.profile_id)
    return ApiResponse(code=0, message="ok", data=result)


@fp_router.post("/profiles/{profile_id}/rollback", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def rollback(profile_id: str, to_version: int = Query(ge=1)):
    """回滚到指定历史版本。"""
    result = store.rollback(profile_id, to_version)
    if not result:
        raise HTTPException(status_code=404, detail="version not found")
    invalidate_cache(profile_id)
    return ApiResponse(code=0, message="ok", data=result)


@fp_router.post("/profiles/{profile_id}/gray", response_model=ApiResponse, dependencies=[Depends(require_admin)])
async def gray(profile_id: str, rollout: RolloutRule):
    """灰度发布。"""
    result = store.update_rollout(profile_id, rollout)
    if not result:
        raise HTTPException(status_code=404, detail="profile not found")
    invalidate_cache(profile_id)
    return ApiResponse(code=0, message="ok", data=result)


@fp_router.get("/nodes/{node_id}/heartbeat", response_model=ApiResponse, dependencies=[Depends(require_node)])
async def heartbeat(
    node_id: str,
    profile_id: Optional[str] = Query(default=None),
    profile_version: Optional[int] = Query(default=None),
    browser: Optional[str] = Query(default=None),
    fp_snapshot: Optional[str] = Query(default=None),
):
    """节点心跳：上报生效画像 + 指纹快照；返回中心最新版本与是否需要刷新。"""
    store.upsert_node(
        node_id,
        {"profile_id": profile_id, "profile_version": profile_version, "browser": browser, "fp_snapshot": fp_snapshot},
    )
    latest_version = store.get_profile_version_number(profile_id or "")
    should_reload = bool(profile_version and latest_version and profile_version < latest_version)
    return ApiResponse(
        code=0,
        message="ok",
        data={"status": "ok", "latest_version": latest_version, "should_reload": should_reload},
    )
