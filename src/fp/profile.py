"""指纹画像数据模型。

与 docs/fp_config_center_api.md 中的 Profile schema 对应。
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from src.config.settings import DEFAULT_UA, DEFAULT_UA_BRAND, DEFAULT_UA_FULL


class FingerprintFields(BaseModel):
    """单个浏览器实例生效的指纹参数（对应 patched Chromium 的 FP_* 环境变量）。"""

    ua: str = Field(DEFAULT_UA, max_length=512)
    ua_full_version: str = DEFAULT_UA_FULL
    ua_brand_version: str = DEFAULT_UA_BRAND
    languages: List[str] = Field(default_factory=lambda: ["zh-CN", "zh"])
    platform: str = "Linux x86_64"
    cores: int = Field(8, ge=1, le=256)
    memory: float = Field(8.0, ge=0.25, le=64)
    webgl_vendor: str = "Intel Inc."
    webgl_renderer: str = "Intel Iris OpenGL Engine"
    canvas_noise: bool = True
    canvas_seed: int = Field(0, ge=0, le=2**32 - 1)
    font_block: List[str] = Field(default_factory=list)
    rtc_ip: str = ""
    audio_noise: bool = True
    audio_rate: int = Field(0, ge=0, le=192000)
    audio_seed: int = Field(0, ge=0, le=2**32 - 1)
    vendor: str = ""
    app_version: str = ""
    dnt: bool = False
    online: str = ""
    net_rtt: int = Field(0, ge=0, le=10000)
    net_downlink: float = Field(0, ge=0, le=1000)
    net_downlink_max: float = Field(0, ge=0, le=1000)
    net_effective_type: str = ""
    screen_width: int = Field(0, ge=0, le=10000)
    screen_height: int = Field(0, ge=0, le=10000)
    screen_color_depth: int = Field(0, ge=0, le=64)
    gl_max_texture_size: int = Field(0, ge=0, le=100000)
    pdf_enabled: int = Field(-1, ge=-1, le=1)
    webrtc_replace_host_ip: bool = True
    touch_points: int = Field(-1, ge=-1, le=20)
    uad_platform: str = "Linux"
    uad_platform_version: str = ""
    uad_arch: str = "x86"
    uad_model: str = ""
    # WebGL 深度伪装（对齐真实 GPU，消除软渲染签名）：
    # webgl_params 键为友好名（MAX_TEXTURE_SIZE 等，见 render.WEBGL_PARAM_ENUMS）
    webgl_params: Dict[str, int] = Field(default_factory=dict)
    webgl_viewport_dims: List[int] = Field(default_factory=list[int])
    webgl_extensions_remove: List[str] = Field(default_factory=list)
    # 平台一致性：时区（与出口 IP 地理位置一致）、电池状态（0..1 / 是否充电中）。
    # 电池未显式指定时按 profile_id 派生稳定值，避免"永远 100% + 永远充电"的 VM 特征。
    timezone: str = ""
    battery_level: Optional[float] = Field(None, ge=0, le=1)
    battery_charging: Optional[bool] = None


class RolloutRule(BaseModel):
    """灰度规则：percent 按节点哈希命中；nodes 显式指定。"""

    percent: int = Field(100, ge=0, le=100)
    nodes: List[str] = Field(default_factory=list)


class FpProfile(BaseModel):
    """指纹画像：标识 + 指纹参数 + 灰度规则。"""

    profile_id: str = Field(min_length=1, max_length=64)
    name: str = ""
    version: int = 1
    enabled: bool = True
    rollout: RolloutRule = RolloutRule()  # type: ignore[reportCallIssue]
    fingerprint: FingerprintFields = FingerprintFields()  # type: ignore[reportCallIssue]

    def is_rolled_out_to(self, node_id: str) -> bool:
        """节点是否命中灰度组。"""
        if not self.enabled:
            return False
        if self.rollout.percent >= 100 and not self.rollout.nodes:
            return True
        if node_id in self.rollout.nodes:
            return True
        if self.rollout.percent <= 0:
            return False
        h = hash(f"{self.profile_id}:{node_id}") % 100
        return h < self.rollout.percent
