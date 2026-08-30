#!/usr/bin/env python3
"""生成 deploy/fonts/fonts-<platform>.conf — 平台字体 fontconfig 配置。

数据源：src/fp/platform_fonts.py（单一来源，与 FP_FONT_BLOCK 黑名单共用）：
- alias：目标平台原生字体 → 容器内度量兼容字体（探测结果为"存在"）
- rejectfont：隐藏容器内不属于目标平台的字体（= BLOCK_BY_PLATFORM 减去 alias
  目标字体——alias 目标必须保持 fontconfig 可解析，枚举屏蔽交给 C++ 层）
- 通用字体族（sans-serif/serif/monospace）按平台固定，保证 CSS 回退可预测

用法：
    uv run python scripts/gen_fontconfig.py [--out DIR]
输出默认覆盖 deploy/fonts/*.conf（由 Dockerfile 拷贝到 /etc/fonts/profiles/）。
tests/test_platform_fonts.py 会重新生成并与提交的 conf 做字节级比对，防漂移。
"""

import argparse
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.fp.platform_fonts import BLOCK_BY_PLATFORM, FONTCONFIG_ALIASES  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy", "fonts")

# 平台 → 通用字体族（CSS font-family: sans-serif/serif/monospace 的固定回退）
GENERIC_ALIASES: Dict[str, Dict[str, str]] = {
    "macos": {
        "sans-serif": "Liberation Sans",
        "serif": "Liberation Serif",
        "monospace": "Liberation Mono",
    },
    "windows": {
        "sans-serif": "Arial",
        "serif": "Times New Roman",
        "monospace": "Courier New",
    },
    "linux": {
        "sans-serif": "DejaVu Sans",
        "serif": "DejaVu Serif",
        "monospace": "DejaVu Sans Mono",
    },
}


def _reject_list(platform: str) -> List[str]:
    """rejectfont 列表 = C++ 黑名单 − alias 目标字体（目标需保持可解析）。

    与 BLOCK_BY_PLATFORM 单一来源对齐：黑名单里新增的字体若同时是 alias 目标，
    只做 C++ 屏蔽（枚举隐藏），不进入 rejectfont（否则 alias 解析失败）。
    """
    rejected = set(BLOCK_BY_PLATFORM.get(platform, BLOCK_BY_PLATFORM["linux"]))
    alias_targets = set(FONTCONFIG_ALIASES.get(platform, {}).values())
    return sorted(rejected - alias_targets)


def _render(platform: str) -> str:
    aliases: Dict[str, str] = FONTCONFIG_ALIASES.get(platform, {})
    generic = GENERIC_ALIASES.get(platform, {})
    rejects = _reject_list(platform)
    lines = [
        '<?xml version="1.0"?>',
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">',
        "<!-- 由 scripts/gen_fontconfig.py 生成：勿手工编辑 -->",
        "<fontconfig>",
        "  <dir>/usr/share/fonts</dir>",
        "  <dir>/usr/local/share/fonts</dir>",
        "  <dir>~/.fonts</dir>",
        "  <cachedir>/var/cache/fontconfig</cachedir>",
        "  <cachedir>~/.cache/fontconfig</cachedir>",
    ]
    if generic:
        lines.append("  <!-- 通用字体族固定回退（替代系统 conf.d 默认） -->")
        for generic_name, target in generic.items():
            lines.extend(
                [
                    "  <alias>",
                    f"    <family>{generic_name}</family>",
                    f"    <prefer><family>{target}</family></prefer>",
                    "  </alias>",
                ]
            )
    if aliases:
        lines.append("  <!-- 目标平台原生字体 → 容器内度量兼容字体 -->")
        for native, target in aliases.items():
            lines.extend(
                [
                    "  <alias>",
                    f"    <family>{native}</family>",
                    f"    <prefer><family>{target}</family></prefer>",
                    "  </alias>",
                ]
            )
    if rejects:
        lines.append("  <!-- 不属于目标平台的容器字体：隐藏（兜底 C++ 黑名单） -->")
        lines.append("  <rejectfont>")
        for family in rejects:
            lines.append(f'    <pattern><patelt name="family"><string>{family}</string></patelt></pattern>')
        lines.append("  </rejectfont>")
    lines.append("</fontconfig>")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="生成平台字体 fontconfig 配置")
    parser.add_argument("--out", default=OUT_DIR, help="输出目录（默认 deploy/fonts）")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for platform in ("macos", "windows", "linux"):
        path = os.path.join(args.out, f"fonts-{platform}.conf")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_render(platform))
        print(f"生成 {os.path.relpath(path)}")


if __name__ == "__main__":
    main()
