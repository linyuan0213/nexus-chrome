#!/usr/bin/env python3
"""生成 patched SwiftShader 库 — 替换 WebGL vendor/renderer/deviceID。

用法:
  python3 scripts/patch_swiftshader.py             # 生成到 patched_libs/
  python3 scripts/patch_swiftshader.py --in-place  # 直接替换 /opt/google/chrome/ (需写权限)
"""

import os
import shutil
import sys

SRC = "/opt/google/chrome/libvk_swiftshader.so"
IN_PLACE = "--in-place" in sys.argv

if IN_PLACE:
    DST = SRC
    shutil.copy2(SRC, SRC + ".bak")
    print(f"已备份: {SRC}.bak")
else:
    DST = os.path.join(os.path.dirname(__file__), "..", "patched_libs", "libvk_swiftshader.so")
    os.makedirs(os.path.dirname(DST), exist_ok=True)

with open(SRC, "rb") as sf:
    data = sf.read()

# 1. vendorID:  0x1AE0 (Google) → 0x8086 (Intel)
# 2. deviceID:  0xC0DE          → 0x5912 (Intel Iris)
# 3. vendor:    "Google"        → "Intel"
# 4. device:    "SwiftShader Device" → "Intel Iris Pro  "
# 5. driver:    "SwiftShader driver" → "Intel Iris drvr"

patches = [
    (0x06c738, b"\x86\x80\x00\x00"),
    (0x06c73c, b"\x12\x59\x00\x00"),
    (0x06cb08, b"\x86\x80\x00\x00"),
    (0x06cb0c, b"\x12\x59\x00\x00"),
]
for offset, value in patches:
    data = data[:offset] + value + data[offset + len(value) :]

replacements = {
    0x48522: b"Intel\x00\x00",
    0x49204: b"Intel Iris Pro  \x00",
    0x4084e: b"Intel Iris drvr\x00\x00\x00",
}
for offset, value in replacements.items():
    data = data[:offset] + value + data[offset + len(value) :]

with open(DST, "wb") as df:
    df.write(data)

print(f"Patched: {DST}")
print("WebGL vendor → Intel, renderer → Intel Iris Pro, driver → Intel Iris drvr")

if IN_PLACE:
    print("\n已直接替换，原始文件已备份为 .bak。无需 unshare bind mount。")
else:
    print(f"\n安装到系统: cp {DST} /opt/google/chrome/libvk_swiftshader.so")
