"""Cookie 请求头合并工具。

静态凭据和运行时 CookieStore 可能同时包含同名 Cookie；直接字符串拼接会让服务端
收到重复的 cf_clearance/Session，导致登录态回退或反复过盾。这里按名称合并，
运行时 Cookie（后传入者）覆盖旧值。
"""

from __future__ import annotations


def merge_cookie_header(existing: str | None, runtime: str | None) -> str:
    """合并两个 Cookie 头，按名称去重，runtime 优先。"""
    values: dict[str, str] = {}
    for header in (existing, runtime):
        if not header:
            continue
        for part in str(header).split(";"):
            chunk = part.strip()
            if not chunk or "=" not in chunk:
                continue
            name, value = chunk.split("=", 1)
            name = name.strip()
            if name:
                values[name] = value.strip()
    return "; ".join(f"{name}={value}" for name, value in values.items())
