"""认证服务 — 用户登录（短期 session token）+ 第三方 API Key（长期可吊销）。

设计要点：
- AUTH_PASSWORD 未设置时认证完全关闭（本地模式，保持现状）。
- 登录签发的是带过期时间的短期 token，而不是直接使用密码当 API token：
  凭证可失效、可轮换、可吊销。
- API Key 只存 SHA-256 摘要，明文仅在创建时返回一次。
- Key 可挂 scope（路径前缀级限权），任何一端泄漏互不影响。
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from threading import RLock
from typing import Any, Dict, List, Optional

from loguru import logger

from src.config.settings import DATA_DIR

AUTH_PASSWORD: Optional[str] = os.getenv("AUTH_PASSWORD") or None
SESSION_TOKEN_TTL = 24 * 3600  # session token 有效期 24h
API_KEY_PREFIX = "ncmk_"

# scope → 允许的路径前缀
SCOPE_PATHS: Dict[str, List[str]] = {
    "sessions": ["/sessions"],
    "instances": ["/instances"],
    "profiles": ["/api/profiles"],
    "*": ["/"],
}


class AuthService:
    def __init__(self, key_file: Optional[str] = None):
        self._key_file = key_file or os.path.join(DATA_DIR, "api_keys.json")
        self._lock = RLock()
        self._sessions: Dict[str, float] = {}  # token → 过期时间
        self._keys: List[Dict[str, Any]] = []
        self._load_keys()

    @property
    def enabled(self) -> bool:
        return AUTH_PASSWORD is not None

    # ---------- 登录（短期 session token） ----------

    def login(self, password: str) -> Optional[str]:
        if not self.enabled or password != AUTH_PASSWORD:
            return None
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = time.time() + SESSION_TOKEN_TTL
        return token

    def logout(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def _verify_session(self, token: str) -> bool:
        with self._lock:
            expiry = self._sessions.get(token)
            if expiry is None:
                return False
            if expiry < time.time():
                self._sessions.pop(token, None)
                return False
            return True

    # ---------- API Key（长期，可吊销） ----------

    def _load_keys(self) -> None:
        if not os.path.exists(self._key_file):
            return
        try:
            with open(self._key_file, "r", encoding="utf-8") as f:
                self._keys = json.load(f).get("keys", [])
        except Exception as e:
            logger.warning(f"加载 API Key 失败: {e}")
            self._keys = []

    def _save_keys(self) -> None:
        os.makedirs(os.path.dirname(self._key_file), exist_ok=True)
        tmp = f"{self._key_file}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"keys": self._keys}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._key_file)

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def create_key(self, name: str, scopes: Optional[List[str]] = None) -> Dict[str, Any]:
        """创建 API Key，返回含明文的记录（明文仅此一次可见）。"""
        plain = API_KEY_PREFIX + secrets.token_urlsafe(24)
        record = {
            "id": secrets.token_hex(4),
            "name": name,
            "prefix": plain[: len(API_KEY_PREFIX) + 6],
            "key_hash": self._hash(plain),
            "scopes": scopes or ["*"],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "revoked": False,
        }
        with self._lock:
            self._keys.append(record)
            self._save_keys()
        return {**record, "key": plain}

    def revoke_key(self, key_id: str) -> bool:
        with self._lock:
            for k in self._keys:
                if k["id"] == key_id and not k["revoked"]:
                    k["revoked"] = True
                    self._save_keys()
                    return True
        return False

    def list_keys(self) -> List[Dict[str, Any]]:
        """列出 Key（不含明文/摘要）。"""
        with self._lock:
            return [{k: v for k, v in rec.items() if k != "key_hash"} for rec in self._keys]

    # ---------- 统一校验 ----------

    def verify(self, token: str, path: str) -> bool:
        """校验凭证是否允许访问 path：session token 或匹配的 API Key。"""
        if self._verify_session(token):
            return True
        return self._verify_api_key(token, path)

    def _verify_api_key(self, token: str, path: str) -> bool:
        if not token.startswith(API_KEY_PREFIX):
            return False
        digest = self._hash(token)
        with self._lock:
            for rec in self._keys:
                if rec["key_hash"] == digest and not rec["revoked"]:
                    return self._scope_allows(rec["scopes"], path)
        return False

    @staticmethod
    def _scope_allows(scopes: List[str], path: str) -> bool:
        for scope in scopes:
            for prefix in SCOPE_PATHS.get(scope, []):
                if path.startswith(prefix):
                    return True
        return False


auth_service = AuthService()
