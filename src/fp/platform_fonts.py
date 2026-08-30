"""平台字体策略 — 按目标平台（macos/windows/linux）约束容器字体指纹。

容器内安装了 Windows/Office 与 Linux 发行字体，直接暴露会给任何伪装平台
造成跨平台矛盾（如 UA 声称 macOS 却探测到 Calibri/SimHei/PMingLiU）。
本模块提供：

1. FP_FONT_BLOCK 黑名单（走 patched Chromium C++ 补丁，无论是否重建镜像
   都生效）：把不属于目标平台的字体族从 document.fonts / canvas 探测中隐藏。
2. FONTCONFIG_FILE 平台字体配置（配合 deploy/fonts/fonts-<platform>.conf）：
   - rejectfont 兜底隐藏（防御 C++ 黑名单未覆盖的字体）
   - alias 把目标平台原生字体名映射到容器内度量兼容字体，使探测结果为
     "该字体存在"（如 macOS 的 Helvetica→Liberation Sans、PingFang SC→
     WenQuanYi Micro Hei），避免目标平台原生字体缺失导致指纹过于单薄。

字体名取自 FingerprintJS 探测候选表（大小写敏感，与 document.fonts.check
传入的族名一致）。
"""

import os
from typing import Dict, List, Tuple

# 字体配置目录（容器内镜像构建时拷贝到该路径；本地无文件时跳过 FONTCONFIG_FILE）
FONT_PROFILE_DIR = os.getenv("FP_FONT_PROFILE_DIR", "/etc/fonts/profiles")

# ---- Windows 专属字体（非 macOS 原生，且容器内可解析或可能被探测） ----
_WINDOWS_MS_CORE = [
    "Arial",
    "Arial Black",
    "Arial Narrow",
    "Arial Rounded MT Bold",
    "Arial Unicode MS",
    "Andale Mono",
    "Book Antiqua",
    "Bookman Old Style",
    "Century Gothic",
    "Century Schoolbook",
    "Comic Sans MS",
    "Courier New",
    "Franklin Gothic Medium",
    "Georgia",
    "Impact",
    "Lucida Console",
    "Marlett",
    "Microsoft Sans Serif",
    "Monotype Corsiva",
    "Palatino Linotype",
    "Symbol",
    "Tahoma",
    "Times New Roman",
    "Trebuchet MS",
    "Verdana",
    "Webdings",
    "Wingdings",
    "Wingdings 2",
    "Wingdings 3",
]

# Windows Office 度量兼容别名（容器经 fontconfig 别名后会被探测为存在）
_WINDOWS_OFFICE_ALIASED = ["Calibri", "Cambria", "Carlito", "Caladea"]

# Windows 中/日/韩系统字体（Mac/Linux 上不存在）
_WINDOWS_CJK = [
    "Batang",
    "BatangChe",
    "Dotum",
    "DotumChe",
    "Ebrima",
    "Gulim",
    "GulimChe",
    "Javanese Text",
    "KaiTi",
    "Latha",
    "Leelawadee UI",
    "Malgun Gothic",
    "Mangal",
    "Meiryo",
    "Microsoft Himalaya",
    "Microsoft JhengHei",
    "Microsoft JhengHei Light",
    "Microsoft New Tai Lue",
    "Microsoft PhagsPa",
    "Microsoft Tai Le",
    "Microsoft YaHei",
    "Microsoft YaHei Light",
    "Microsoft Yi Baiti",
    "MingLiU-ExtB",
    "MingLiU_HKSCS-ExtB",
    "Mongolian Baiti",
    "MS Gothic",
    "MS Outlook",
    "MS PGothic",
    "MS Reference Sans Serif",
    "MS Reference Specialty",
    "MS UI Gothic",
    "MT Extra",
    "MV Boli",
    "Myanmar Text",
    "Narkisim",
    "Nirmala UI",
    "PMingLiU",
    "PMingLiU-ExtB",
    "Raavi",
    "Segoe Print",
    "Segoe Script",
    "Segoe UI",
    "Segoe UI Black",
    "Segoe UI Emoji",
    "Segoe UI Historic",
    "Segoe UI Light",
    "Segoe UI Semibold",
    "Segoe UI Semilight",
    "Segoe UI Symbol",
    "SimHei",
    "SimSun",
    "SimSun-ExtB",
    "Simplified Arabic",
    "Simplified Arabic Fixed",
    "Sylfaen",
    "Urdu Typesetting",
    "Vijaya",
    "Vrinda",
    "Yu Gothic",
    "Yu Mincho",
]

# 其余 Windows Office 装饰字体（容器未安装但被探测，屏蔽保持平台纯净）。
# Lucida Sans / Lucida Bright 也随 macOS（Office for Mac）发行，是 macos 平台
# 的 alias 源字体，不能算 Windows-only，故不在此列表。
_WINDOWS_OFFICE_EXTRA = [
    "Bahnschrift",
    "Bahnschrift Condensed",
    "Bahnschrift SemiCondensed",
    "Bauhaus 93",
    "Bodoni MT",
    "Bodoni MT Black",
    "Bodoni MT Condensed",
    "Bodoni MT Poster Compressed",
    "Bradley Hand ITC",
    "Broadway",
    "Brush Script MT",
    "Cascadia Code",
    "Cascadia Mono",
    "Castellar",
    "Chiller",
    "Colonna MT",
    "Cooper Black",
    "Copperplate Gothic Bold",
    "Copperplate Gothic Light",
    "Ebrima",
    "Edwardian Script ITC",
    "Elephant",
    "Engravers MT",
    "Eras Bold ITC",
    "Eras Demi ITC",
    "Eras Light ITC",
    "Eras Medium ITC",
    "Felix Titling",
    "Footlight MT Light",
    "Franklin Gothic Book",
    "Franklin Gothic Demi",
    "Franklin Gothic Demi Cond",
    "Franklin Gothic Heavy",
    "Franklin Gothic Medium Cond",
    "Gabriola",
    "Gigi",
    "Gill Sans MT",
    "Gill Sans MT Condensed",
    "Gill Sans MT Ext Condensed Bold",
    "Gill Sans Ultra Bold",
    "Gill Sans Ultra Bold Condensed",
    "Gloucester MT Extra Condensed",
    "Goudy Old Style",
    "Goudy Stout",
    "Haettenschweiler",
    "Harlow Solid Italic",
    "Harrington",
    "High Tower Text",
    "Imprint MT Shadow",
    "Informal Roman",
    "Ink Free",
    "Jokerman",
    "Juice ITC",
    "Kristen ITC",
    "Kunstler Script",
    "Lucida Bright",
    "Lucida Calligraphy",
    "Lucida Fax",
    "Lucida Handwriting",
    "Lucida Sans Typewriter",
    "Lucida Sans Unicode",
    "Magneto",
    "Maiandra GD",
    "Matura MT Script Capitals",
    "Mistral",
    "Modern",
    "Modern No. 20",
    "Monotype Corsiva",
    "OCR A Extended",
    "OCR A Std",
    "Old English Text MT",
    "Onyx",
    "Palace Script MT",
    "Parchment",
    "Perpetua",
    "Perpetua Titling MT",
    "Playbill",
    "Poor Richard",
    "Pristina",
    "Rage Italic",
    "Ravi Prakash",
    "Rockwell",
    "Rockwell Condensed",
    "Rockwell Extra Bold",
    "Script MT Bold",
    "Showcard Gothic",
    "Sitka Banner",
    "Sitka Black",
    "Sitka Display",
    "Sitka Heading",
    "Sitka Small",
    "Sitka Subheading",
    "Sitka Text",
    "Stencil",
    "Tempus Sans ITC",
    "Tw Cen MT",
    "Tw Cen MT Condensed",
    "Tw Cen MT Condensed Extra Bold",
    "Viner Hand ITC",
    "Vivaldi",
    "Vladimir Script",
    "Wide Latin",
]

# ---- macOS 专属字体（Windows/Linux 上不存在） ----
_MACOS_FONTS = [
    "American Typewriter",
    "Apple Color Emoji",
    "Apple Symbols",
    "Avenir",
    "Avenir Next",
    "Baskerville",
    "Big Caslon",
    "Bodoni 72",
    "Chalkboard",
    "Chalkboard SE",
    "Charter",
    "Cochin",
    "Courier",
    "Didot",
    "Futura",
    "Geneva",
    "Gill Sans",
    "Helvetica",
    "Helvetica Neue",
    "Herculanum",
    "Hiragino Kaku Gothic ProN",
    "Hiragino Maru Gothic ProN",
    "Hiragino Mincho ProN",
    "Hiragino Sans",
    "Hiragino Sans GB",
    "Hoefler Text",
    "Kaiti SC",
    "Lucida Grande",
    "Marker Felt",
    "Menlo",
    "Monaco",
    "Optima",
    "Palatino",
    "Papyrus",
    "PingFang HK",
    "PingFang SC",
    "PingFang TC",
    "Sabon",
    "Savoye LET",
    "Skia",
    "Snell Roundhand",
    "Songti SC",
    "STHeiti",
    "Zapfino",
]

# ---- 容器内 Linux 发行字体（目标平台非 Linux 时屏蔽） ----
_LINUX_FONTS = [
    "DejaVu Sans",
    "DejaVu Sans Condensed",
    "DejaVu Sans Light",
    "DejaVu Sans Mono",
    "DejaVu Serif",
    "DejaVu Serif Condensed",
    "DejaVu Serif Italic",
    "FreeMono",
    "FreeSans",
    "FreeSerif",
    "Liberation Mono",
    "Liberation Sans",
    "Liberation Serif",
    "Noto Color Emoji",
    "Noto Sans",
    "Noto Sans CJK JP",
    "Noto Sans CJK KR",
    "Noto Sans CJK SC",
    "Noto Sans CJK TC",
    "Noto Sans Mono",
    "Noto Sans Symbols",
    "Noto Serif CJK JP",
    "Noto Serif CJK KR",
    "Noto Serif CJK SC",
    "Noto Serif CJK TC",
]

# macOS 原生也存在的 Windows 核心字体（macos 平台不屏蔽）
_MACOS_SAFE_MS_CORE = {
    "Arial",
    "Arial Black",
    "Arial Narrow",
    "Arial Rounded MT Bold",
    "Arial Unicode MS",
    "Andale Mono",
    "Comic Sans MS",
    "Courier New",
    "Georgia",
    "Impact",
    "Symbol",
    "Times New Roman",
    "Trebuchet MS",
    "Verdana",
}

# 容器内中文字体（作 CJK alias 目标，需保持 fontconfig 可解析，仅 C++ 层屏蔽枚举）。
# macOS/Windows 不安装这些字体，直接暴露会被 document.fonts 枚举识别为跨平台泄漏；
# 但 alias（如 SimHei→WenQuanYi Micro Hei）依赖其可解析，因此不能进 rejectfont。
_CONTAINER_CJK_ALIAS_TARGETS = [
    "WenQuanYi Micro Hei",
    "WenQuanYi Micro Hei Mono",
    "WenQuanYi Zen Hei",
    "WenQuanYi Zen Hei Mono",
    "WenQuanYi Zen Hei Sharp",
]

# 平台 → FP_FONT_BLOCK 黑名单（C++ 补丁隐藏 document.fonts/canvas 探测）
BLOCK_BY_PLATFORM: Dict[str, List[str]] = {
    "macos": sorted(
        set(_WINDOWS_MS_CORE) - _MACOS_SAFE_MS_CORE
        | set(_WINDOWS_OFFICE_ALIASED)
        | set(_WINDOWS_CJK)
        | set(_WINDOWS_OFFICE_EXTRA)
        | set(_LINUX_FONTS)
        | set(_CONTAINER_CJK_ALIAS_TARGETS)
    ),
    "windows": sorted(set(_MACOS_FONTS) | set(_LINUX_FONTS) | set(_CONTAINER_CJK_ALIAS_TARGETS)),
    "linux": sorted(
        set(_WINDOWS_MS_CORE)
        | (set(_WINDOWS_OFFICE_ALIASED) - {"Carlito", "Caladea"})
        | set(_WINDOWS_CJK)
        | set(_WINDOWS_OFFICE_EXTRA)
        | set(_MACOS_FONTS)
    ),
}

# 平台 → fontconfig alias（目标平台原生字体 → 容器内度量兼容字体）。
# 目标字体必须未被对应平台 rejectfont（见 deploy/fonts/*.conf）。
FONTCONFIG_ALIASES: Dict[str, Dict[str, str]] = {
    "macos": {
        "Helvetica": "Liberation Sans",
        "Helvetica Neue": "Liberation Sans",
        "Lucida Grande": "Liberation Sans",
        "Geneva": "Arial",
        "Courier": "Liberation Mono",
        "Monaco": "Liberation Mono",
        "Menlo": "Liberation Mono",
        "Palatino": "Liberation Serif",
        "Times": "Times New Roman",
        # FingerprintJS 探测列表中的 macOS 常见字体（Gill Sans 为 Mac 核心字体，
        # Lucida/Minion 为 Office/Adobe 装机会带），alias 使其探测为"存在"
        "Gill Sans": "Liberation Sans",
        "Lucida Sans": "Liberation Sans",
        "Lucida Bright": "Liberation Serif",
        "Minion Pro": "Liberation Serif",
        "PingFang SC": "WenQuanYi Micro Hei",
        "PingFang TC": "WenQuanYi Micro Hei",
        "Hiragino Sans GB": "WenQuanYi Micro Hei",
        "Hiragino Kaku Gothic ProN": "WenQuanYi Micro Hei",
        "STHeiti": "WenQuanYi Micro Hei",
        "Songti SC": "WenQuanYi Micro Hei",
        "Kaiti SC": "WenQuanYi Micro Hei",
    },
    "windows": {
        "Calibri": "Carlito",
        "Cambria": "Caladea",
        "SimHei": "WenQuanYi Micro Hei",
        "SimSun": "WenQuanYi Micro Hei",
        "PMingLiU": "WenQuanYi Micro Hei",
        "Microsoft YaHei": "WenQuanYi Micro Hei",
        "Microsoft JhengHei": "WenQuanYi Micro Hei",
        "KaiTi": "WenQuanYi Micro Hei",
        "MS Gothic": "WenQuanYi Micro Hei",
        "MS PGothic": "WenQuanYi Micro Hei",
        "Meiryo": "WenQuanYi Micro Hei",
        "Yu Gothic": "WenQuanYi Micro Hei",
        "Yu Mincho": "WenQuanYi Micro Hei",
        "Malgun Gothic": "WenQuanYi Micro Hei",
    },
    "linux": {},
}


def platform_font_config(platform: str) -> Tuple[List[str], str]:
    """返回目标平台的 (FP_FONT_BLOCK 黑名单, FONTCONFIG_FILE 路径)。

    FONTCONFIG_FILE 指向 deploy/fonts/fonts-<platform>.conf；文件不存在时
    （未重建镜像/本地开发）返回空串，调用方跳过，仅靠 C++ 黑名单兜底。
    """
    block = BLOCK_BY_PLATFORM.get(platform, BLOCK_BY_PLATFORM["linux"])
    conf = os.path.join(FONT_PROFILE_DIR, f"fonts-{platform}.conf")
    return list(block), conf if os.path.isfile(conf) else ""


def merge_font_block(explicit: List[str], platform_block: List[str]) -> List[str]:
    """合并画像显式黑名单与平台策略：显式名单优先，平台策略兜底补齐。"""
    merged: List[str] = []
    for name in list(explicit) + platform_block:
        if name and name not in merged:
            merged.append(name)
    return merged
