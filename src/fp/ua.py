"""UA 字段派生助手 —— 支持接收任意 UA（含与当前 Chromium 基线无关的版本）。

画像/会话只需提供一个合法 UA 字符串即可，brand/fullVersion 会从 UA 的
`Chrome/<major>...` 段自动派生，保证 JS userAgentData 与网络层
Sec-CH-UA-*（brands/fullVersionList）与 UA 声明一致，无需人工三件套对齐。
显式提供的 ua_full/ua_brand 优先于派生值。
"""

import re

_CHROME_MAJOR_RE = re.compile(r"\bChrome/(\d+)\.")


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
