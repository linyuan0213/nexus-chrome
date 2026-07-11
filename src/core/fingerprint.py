"""指纹管理器 — 预置 3 种 profile，支持自定义扩展。"""

from typing import Any, Dict, List, Optional

from src.config.settings import (
    DEFAULT_FINGERPRINT_PROFILE,
    FINGERPRINT_PROFILES,
)


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

    def get_init_js(self) -> str:
        scripts = self._config.get("js_scripts", [])
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
