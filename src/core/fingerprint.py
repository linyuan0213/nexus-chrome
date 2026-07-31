"""指纹管理器 — 预置 3 种 profile，支持自定义扩展。"""

import re
from typing import Any, Dict, List, Optional

from src.config.settings import (
    DEFAULT_FINGERPRINT_PROFILE,
    FINGERPRINT_PROFILES,
)

# 兜底版本（当无法从 User-Agent 解析出真实 Chrome 版本时使用）
_FALLBACK_BRAND_VERSION = "149"
_FALLBACK_FULL_VERSION = "149.0.7827.53"


def _extract_chrome_version(user_agent: str) -> str:
    """从 User-Agent 提取完整 Chrome 版本号，如 '149.0.7827.53'。"""
    m = re.search(r"Chrome/(\d+)\.(\d+)\.(\d+)\.(\d+)", user_agent)
    if not m:
        return _FALLBACK_FULL_VERSION
    return ".".join(m.groups())


class FingerprintManager:
    PROFILES: Dict[str, Dict[str, Any]] = FINGERPRINT_PROFILES

    def __init__(self, profile_name: Optional[str] = None):
        name = profile_name or DEFAULT_FINGERPRINT_PROFILE
        if name not in self.PROFILES:
            raise ValueError(f"未知指纹 profile: {name}，可用: {list(self.PROFILES.keys())}")
        self.profile_name = name
        self._config = self.PROFILES[name]

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    def get_init_js(self, user_agent: Optional[str] = None) -> str:
        """构造注入脚本；传入真实 User-Agent 时会让 Chrome 版本号与浏览器一致。"""
        full_version = _extract_chrome_version(user_agent or "")
        major_version = full_version.split(".", 1)[0]
        scripts: List[str] = []
        for raw in self._config.get("js_scripts", []):
            script = str(raw)
            script = script.replace("__CHROME_BRAND__", major_version)
            script = script.replace("__CHROME_FULL__", full_version)
            scripts.append(script)
        return "\n".join(scripts)

    def get_browser_args(self) -> List[str]:
        args: List[str] = []
        if self._config.get("disable_webgl"):
            args.append("--disable-webgl")
        args.extend(self._config.get("browser_args", []))
        return args

    def get_disable_features(self) -> List[str]:
        return self._config.get("disable_features", [])

    @classmethod
    def register_profile(cls, name: str, config: Dict[str, Any]) -> None:
        cls.PROFILES[name] = config

    @classmethod
    def list_profiles(cls) -> List[str]:
        return list(cls.PROFILES.keys())
