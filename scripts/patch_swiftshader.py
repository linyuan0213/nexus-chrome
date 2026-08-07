#!/usr/bin/env python3
"""生成/伪装 SwiftShader 库 — 动态模式匹配，适配任意架构与 Chrome/Chromium 版本。

用法:
  python3 scripts/patch_swiftshader.py                # 自动定位并原地伪装（带 .orig 备份）
  python3 scripts/patch_swiftshader.py --lib /path/to/libvk_swiftshader.so  # 指定文件
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.swiftshader_patch import main  # noqa: E402

if __name__ == "__main__":
    main()
