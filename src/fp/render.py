"""指纹画像 → FP_* 环境变量渲染。

patched Chromium 的 fp_config.h 在 Blink 渲染进程通过 getenv 读取这些环境变量
（渲染进程继承浏览器进程环境）。列表字段用逗号连接。
"""

from typing import Dict, Optional

from src.fp.profile import FingerprintFields

# Profile 字段 → 环境变量名
ENV_MAP: Dict[str, str] = {
    "ua": "FP_UA",
    "ua_full_version": "FP_UA_FULL",
    "ua_brand_version": "FP_UA_BRAND",
    "platform": "FP_PLATFORM",
    "cores": "FP_CORES",
    "memory": "FP_MEMORY",
    "webgl_vendor": "FP_WEBGL_VENDOR",
    "webgl_renderer": "FP_WEBGL_RENDERER",
    "canvas_noise": "FP_CANVAS_NOISE",
    "canvas_seed": "FP_CANVAS_SEED",
    "audio_noise": "FP_AUDIO_NOISE",
    "dnt": "FP_DNT",
    "online": "FP_ONLINE",
    "audio_seed": "FP_AUDIO_SEED",
    "audio_rate": "FP_AUDIO_RATE",
    "vendor": "FP_VENDOR",
    "app_version": "FP_APP_VERSION",
    "net_rtt": "FP_NET_RTT",
    "net_downlink": "FP_NET_DOWNLINK",
    "net_downlink_max": "FP_NET_DOWNLINK_MAX",
    "net_effective_type": "FP_NET_EFFECTIVE_TYPE",
    "screen_width": "FP_SCREEN_WIDTH",
    "screen_height": "FP_SCREEN_HEIGHT",
    "screen_color_depth": "FP_SCREEN_COLOR_DEPTH",
    "gl_max_texture_size": "FP_GL_MAX_TEXTURE_SIZE",
    "pdf_enabled": "FP_PDF_ENABLED",
    "webrtc_replace_host_ip": "FP_WEBRTC_REPLACE_HOST_IP",
    "touch_points": "FP_TOUCH_POINTS",
    "uad_platform": "FP_UAD_PLATFORM",
    "uad_platform_version": "FP_UAD_PLATFORM_VERSION",
    "uad_arch": "FP_UAD_ARCH",
    "uad_model": "FP_UAD_MODEL",
}

# 列表字段 → 环境变量名（逗号连接）
LIST_ENV_MAP: Dict[str, str] = {
    "languages": "FP_LANGS",
    "font_block": "FP_FONT_BLOCK",
}


def render_env(fingerprint: FingerprintFields, profile_id: Optional[str] = None) -> Dict[str, str]:
    """将指纹参数渲染为 FP_* 环境变量字典（不含空值）。

    profile_id 会写入 FP_PROFILE_ID，供 patched Chromium 的 CanvasSeed
    按画像生成种子（同一画像内画布指纹一致，不同画像不同）。
    """
    env: Dict[str, str] = {}
    if profile_id:
        env["FP_PROFILE_ID"] = profile_id
    for key, var in ENV_MAP.items():
        value = getattr(fingerprint, key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            env[var] = "1" if value else "0"
        else:
            env[var] = str(value)
    for key, var in LIST_ENV_MAP.items():
        value = getattr(fingerprint, key)
        if value:
            env[var] = ",".join(value)
    return env
