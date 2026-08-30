"""认证路由 — 登录/登出/API Key 管理。

登录/登出/config 不经过全局中间件校验；me 与 keys 由中间件保护。
"""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.api.schemas import ApiResponse
from src.config.settings import VNC_ENABLED, VNC_PASSWORD
from src.core.auth import auth_service

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class CreateKeyRequest(BaseModel):
    name: str
    scopes: list[str] = ["*"]


@auth_router.get("/config", response_model=ApiResponse)
async def auth_config():
    """前端启动探测：是否需要登录（无需认证）。"""
    return ApiResponse(code=0, message="ok", data={"enabled": auth_service.enabled})


@auth_router.post("/login", response_model=ApiResponse)
async def login(req: LoginRequest):
    token = auth_service.login(req.password)
    if token is None:
        raise HTTPException(status_code=401, detail="密码错误")
    return ApiResponse(code=0, message="ok", data={"token": token})


@auth_router.post("/logout", response_model=ApiResponse)
async def logout(authorization: str = Header(default="", alias="Authorization")):
    if authorization.startswith("Bearer "):
        auth_service.logout(authorization[7:])
    return ApiResponse(code=0, message="ok", data=None)


@auth_router.get("/me", response_model=ApiResponse)
async def me():
    """当前认证状态 + 前端安全配置（VNC 密码等，仅认证后可访问——由中间件保护）。"""
    return ApiResponse(
        code=0,
        message="ok",
        data={
            "vnc_enabled": VNC_ENABLED,
            "vnc_password": VNC_PASSWORD if VNC_ENABLED else None,
        },
    )


@auth_router.get("/keys", response_model=ApiResponse)
async def list_keys():
    return ApiResponse(code=0, message="ok", data={"keys": auth_service.list_keys()})


@auth_router.post("/keys", response_model=ApiResponse)
async def create_key(req: CreateKeyRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="名称不能为空")
    record = auth_service.create_key(req.name.strip(), req.scopes)
    return ApiResponse(code=0, message="ok", data=record)


@auth_router.delete("/keys/{key_id}", response_model=ApiResponse)
async def revoke_key(key_id: str):
    if not auth_service.revoke_key(key_id):
        raise HTTPException(status_code=404, detail="Key 不存在或已吊销")
    return ApiResponse(code=0, message="已吊销", data=None)
