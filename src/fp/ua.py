"""UA 字段派生助手 —— 支持接收任意 UA（含与当前 Chromium 基线无关的版本）。

画像/会话只需提供一个合法 UA 字符串即可，brand/fullVersion 会从 UA 的
`Chrome/<major>...` 段自动派生，保证 JS userAgentData 与网络层
Sec-CH-UA-*（brands/fullVersionList）与 UA 声明一致，无需人工三件套对齐。
显式提供的 ua_full/ua_brand 优先于派生值。
"""

import re

_CHROME_MAJOR_RE = re.compile(r"\bChrome/(\d+)\.")

# UA 平台标记 → (navigator.platform, Sec-CH-UA-Platform / userAgentData.platform)
# 顺序敏感：iOS/Android 必须排在 Linux/Macintosh 之前。
_PLATFORM_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("iPhone",), "iPhone", "iOS"),
    (("iPad",), "iPad", "iOS"),
    (("iPod",), "iPod", "iOS"),
    (("Android",), "Linux armv8l", "Android"),
    (("Windows",), "Win32", "Windows"),
    (("Macintosh", "Mac OS X"), "MacIntel", "macOS"),
    (("CrOS",), "Linux x86_64", "Chrome OS"),
    (("Linux",), "Linux x86_64", "Linux"),
)


def derive_platform(ua: str | None) -> dict[str, str]:
    """从 UA 推导 JS `navigator.platform` 与 UA-CH 平台，保证与 UA 声明自洽。

    会话级 UA 覆盖（CreateSessionRequest.user_agent）过去只改 UA 字符串，
    `navigator.platform` 仍由实例启动时的指纹 env 决定，导致「UA 说 Mac、
    platform 说 Linux」的矛盾，被 Cloudflare Turnstile 判定为异常而拒绝渲染。
    无识别结果时返回空 dict，交由调用方回退实例原值。
    """
    if not ua:
        return {}
    for markers, js_platform, uad_platform in _PLATFORM_RULES:
        if any(marker in ua for marker in markers):
            return {"js_platform": js_platform, "uad_platform": uad_platform}
    return {}


def ua_major(ua: str) -> str | None:
    m = _CHROME_MAJOR_RE.search(ua)
    return m.group(1) if m else None


def derive_full_version(ua: str, ua_full: str | None = None) -> str | None:
    if ua_full:
        return ua_full
    major = ua_major(ua)
    return f"{major}.0.0.0" if major else None


def derive_brand_version(ua: str, ua_brand: str | None = None) -> str | None:
    if ua_brand:
        return ua_brand
    return ua_major(ua)


def resolve_ua_fields(ua: str | None, ua_full: str | None = None, ua_brand: str | None = None) -> dict[str, str | None]:
    """把「任意 UA + 可选 full/brand」归一为自洽三元组（缺失项按 UA major 派生）。"""
    if not ua:
        return {"ua": ua, "ua_full": ua_full, "ua_brand": ua_brand}
    return {
        "ua": ua,
        "ua_full": derive_full_version(ua, ua_full),
        "ua_brand": derive_brand_version(ua, ua_brand),
    }


def ua_identity(ua: str | None) -> dict[str, str | None]:
    """提取 UA 的「身份标识」：UA-CH 平台 + Chrome 主版本。

    这两个字段决定画像指纹（补丁 Chromium 的 userAgentData / WebGL 渲染栈）是否
    与 UA 自洽。无法识别时对应字段为 None。
    """
    if not ua:
        return {"uad_platform": None, "chrome_major": None}
    return {
        "uad_platform": derive_platform(ua).get("uad_platform"),
        "chrome_major": ua_major(ua),
    }


def profile_fits_ua(fp_env: dict[str, str] | None, ua: str | None) -> bool:
    """画像 env 的「平台 + Chrome 主版本」是否与 UA 一致。

    补丁 Chromium 的 `navigator.userAgentData.*` 与 WebGL 渲染栈由画像 env 决定
    （CDP 只能改 `navigator.userAgent` / 旧版 `navigator.platform`），因此会话 UA
    的平台/主版本必须与画像一致，否则会出现「UA 说 Windows、userAgentData 说
    Linux、WebGL 泄漏 Mesa」的自相矛盾，被 Cloudflare Turnstile 直接拒绝。

    UA 不含可识别字段时不做限制（返回 True）。缺失画像 env 视为无法判定（True），
    由调用方决定是否按 UA 重新绑定画像。
    """
    if not fp_env or not ua:
        return True
    ident = ua_identity(ua)
    if ident["uad_platform"] and fp_env.get("FP_UAD_PLATFORM") != ident["uad_platform"]:
        return False
    if ident["chrome_major"] and fp_env.get("FP_UA_BRAND") != ident["chrome_major"]:
        return False
    return True
