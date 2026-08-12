"""指纹画像 → FP_* 环境变量渲染。

patched Chromium 的 fp_config.h 在 Blink 渲染进程通过 getenv 读取这些环境变量
（渲染进程继承浏览器进程环境）。列表字段用逗号连接。
"""

from typing import Dict, List, Optional

from loguru import logger

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
    "webgl_extensions_remove": "FP_WEBGL_EXTENSIONS_REMOVE",
}

# WebGL 参数友好名 → 十进制 GLenum（仅允许返回标量的 MAX_* 类参数）
WEBGL_PARAM_ENUMS: Dict[str, int] = {
    "MAX_TEXTURE_SIZE": 3379,
    "MAX_VIEWPORT_DIMS": 3386,
    "MAX_3D_TEXTURE_SIZE": 32883,
    "MAX_RENDERBUFFER_SIZE": 34024,
    "MAX_TEXTURE_MAX_ANISOTROPY": 34047,
    "MAX_CUBE_MAP_TEXTURE_SIZE": 34076,
    "MAX_VERTEX_ATTRIBS": 34921,
    "MAX_TEXTURE_IMAGE_UNITS": 34930,
    "MAX_ARRAY_TEXTURE_LAYERS": 35071,
    "MAX_VERTEX_UNIFORM_BLOCKS": 35371,
    "MAX_FRAGMENT_UNIFORM_BLOCKS": 35373,
    "MAX_UNIFORM_BUFFER_BINDINGS": 35375,
    "MAX_VERTEX_TEXTURE_IMAGE_UNITS": 35660,
    "MAX_COMBINED_TEXTURE_IMAGE_UNITS": 35661,
    "MAX_VARYING_COMPONENTS": 35659,
    "MAX_TRANSFORM_FEEDBACK_SEPARATE_ATTRIBS": 35979,
    "MAX_SAMPLES": 36183,
    "MAX_ELEMENT_INDEX": 36203,
    "MAX_VERTEX_UNIFORM_VECTORS": 36347,
    "MAX_VARYING_VECTORS": 36348,
    "MAX_FRAGMENT_UNIFORM_VECTORS": 36349,
}


def _detect_platform(fingerprint: FingerprintFields) -> str:
    """从画像字段推断目标平台：macos / windows / linux。"""
    p = (fingerprint.platform or "").lower()
    ua = (fingerprint.ua or "").lower()
    if "mac" in p or "macintosh" in ua or "mac os" in ua:
        return "macos"
    if "win" in p or "windows" in ua:
        return "windows"
    return "linux"


def _auto_webgl_params(fingerprint: FingerprintFields) -> Dict[str, int]:
    """画像未显式设置 webgl_params 时，按目标 GPU 平台自动生成自洽参数。

    所有真实 GPU 都满足的基础值 + 平台差异值。不含 MAX_RENDERBUFFER_SIZE
    （上越声明曾在 legacy 渲染路径触发 GPU 段错误）。
    """
    platform = _detect_platform(fingerprint)
    params: Dict[str, int] = {
        "MAX_VERTEX_ATTRIBS": 16,
        "MAX_TEXTURE_SIZE": 16384,
        "MAX_CUBE_MAP_TEXTURE_SIZE": 16384,
        "MAX_3D_TEXTURE_SIZE": 2048,
        "MAX_ARRAY_TEXTURE_LAYERS": 2048,
        "MAX_VERTEX_UNIFORM_VECTORS": 4096,
        "MAX_VARYING_VECTORS": 31,
        "MAX_TEXTURE_IMAGE_UNITS": 16,
        "MAX_VERTEX_TEXTURE_IMAGE_UNITS": 16,
        "MAX_SAMPLES": 4,
        "MAX_ELEMENT_INDEX": 4294967294,
    }
    if platform == "windows":
        # ANGLE D3D11：fragment 常量 1024、组合纹理单元 32、viewport 32767
        params["MAX_FRAGMENT_UNIFORM_VECTORS"] = 1024
        params["MAX_COMBINED_TEXTURE_IMAGE_UNITS"] = 32
        params["MAX_VARYING_COMPONENTS"] = 120
        params["MAX_UNIFORM_BUFFER_BINDINGS"] = 24
    elif platform == "macos":
        # ANGLE Metal：fragment 常量 4096、组合纹理单元 80
        params["MAX_FRAGMENT_UNIFORM_VECTORS"] = 4096
        params["MAX_COMBINED_TEXTURE_IMAGE_UNITS"] = 80
    else:  # linux / Mesa
        params["MAX_FRAGMENT_UNIFORM_VECTORS"] = 4096
        params["MAX_COMBINED_TEXTURE_IMAGE_UNITS"] = 192
    return params


def _auto_viewport_dims(fingerprint: FingerprintFields) -> List[int]:
    """画像未设 webgl_viewport_dims 时按平台生成：Windows/D3D11 32767，其余 16384。"""
    return [32767, 32767] if _detect_platform(fingerprint) == "windows" else [16384, 16384]


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
    # WebGL 标量参数覆盖 → "十进制GLenum:值,..."（未知名跳过并告警）
    webgl_params = fingerprint.webgl_params
    if not webgl_params and (fingerprint.webgl_renderer or fingerprint.platform):
        webgl_params = _auto_webgl_params(fingerprint)
        logger.debug(f"[fp] 画像未设 webgl_params，按 {_detect_platform(fingerprint)} 自动生成: {sorted(webgl_params)}")
    if webgl_params:
        pairs: list[str] = []
        for name, val in webgl_params.items():
            enum = WEBGL_PARAM_ENUMS.get(name)
            if enum is None:
                logger.warning(f"[fp] 未知 WebGL 参数名 {name}，已跳过")
                continue
            pairs.append(f"{enum}:{val}")
        if pairs:
            env["FP_WEBGL_PARAMS"] = ",".join(pairs)
    # MAX_VIEWPORT_DIMS 二维覆盖（画像未设时按平台自动生成）
    viewport_dims = fingerprint.webgl_viewport_dims
    if len(viewport_dims) != 2 and (fingerprint.webgl_renderer or fingerprint.platform):
        viewport_dims = _auto_viewport_dims(fingerprint)
    if len(viewport_dims) == 2:
        env["FP_WEBGL_VIEWPORT_DIMS"] = f"{viewport_dims[0]},{viewport_dims[1]}"
    return env
