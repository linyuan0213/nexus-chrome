"""HMAC-SHA256 配置签名 — 中心下发时签名，节点验签后使用。

签名密钥通过环境变量 FP_CENTER_SECRET 注入（中心与节点共享同一密钥）。
"""

import hashlib
import hmac
import json
import os
from typing import Any

FP_CENTER_SECRET: str = os.getenv("FP_CENTER_SECRET", "")


def sign_payload(data: dict[str, Any], version: int, secret: str = FP_CENTER_SECRET) -> str:
    """对配置数据签名：HMAC_SHA256(secret, canonical(data) + "|" + version)。"""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    message = f"{canonical}|{version}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_payload(data: dict[str, Any], version: int, signature: str, secret: str = FP_CENTER_SECRET) -> bool:
    if not secret or not signature:
        return False
    expected = sign_payload(data, version, secret)
    return hmac.compare_digest(expected, signature)
