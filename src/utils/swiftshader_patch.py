"""动态 SwiftShader 伪装 — 按模式定位并原地 patch，适配任意架构/版本的 Chrome 或 Chromium。

原理：不再依赖硬编码二进制偏移（偏移会随版本漂移），而是直接在二进制中
按字节模式搜索并替换，因此对 Google Chrome（amd64）、Debian/Ubuntu Chromium
（arm64）以及任何版本都有效：

- vendorID ``0x1AE0``(Google) → ``0x8086``(Intel)
- deviceID ``0xC0DE``(SwiftShader) → ``0x5912``(Intel Iris)
- 字符串 ``Google`` → ``Intel``、``SwiftShader Device`` → ``Intel Iris Pro``、
  ``SwiftShader driver`` → ``Intel Iris drvr``（等长替换，不改变文件长度）

所有替换都是“只覆盖不位移”，保证二进制结构不变；原地写入前先备份为 ``.orig``。
"""

import glob
import os
import shutil
from typing import Dict, List, Optional, Tuple

from loguru import logger

# 物理设备 ID（小端字节序，amd64 与 arm64 均适用）
VENDOR_GOOGLE = b"\xe0\x1a\x00\x00"  # 0x1AE0
VENDOR_INTEL = b"\x86\x80\x00\x00"  # 0x8086
DEVICE_SWIFTSHADER = b"\xde\xc0\x00\x00"  # 0xC0DE
DEVICE_INTEL_IRIS = b"\x12\x59\x00\x00"  # 0x5912

# 字符串替换（等长填充，避免改变文件长度）
STRING_PATCHES: List[Tuple[bytes, bytes]] = [
    (b"Google", b"Intel"),
    (b"SwiftShader Device", b"Intel Iris Pro    "),  # 18 字节等长
    (b"SwiftShader driver", b"Intel Iris drvr   "),  # 18 字节等长
]

# 常见安装路径：Google Chrome / Debian Chromium / Ubuntu chromium-browser /
# snap / flatpak，支持 lib 位于顶层或子目录（如 /opt/google/chrome/lib64/）。
GLOB_PATTERNS: List[str] = [
    "/opt/google/chrome/libvk_swiftshader.so",
    "/opt/google/chrome/**/libvk_swiftshader.so",
    "/usr/lib/chromium/libvk_swiftshader.so",
    "/usr/lib/chromium/**/libvk_swiftshader.so",
    "/usr/lib/chromium-browser/libvk_swiftshader.so",
    "/usr/lib/chromium-browser/**/libvk_swiftshader.so",
    "/snap/chromium/*/usr/lib/chromium-browser/libvk_swiftshader.so",
    "/var/lib/flatpak/**/libvk_swiftshader.so",
]


def _replace_keep_length(data: bytes, old: bytes, new: bytes) -> Tuple[bytes, int]:
    """在字节串中做“等长”替换（new 短则填充空格），不改变总长度。"""
    if len(new) > len(old):
        raise ValueError(f"替换串过长: {old!r} -> {new!r}")
    rep = new.ljust(len(old))
    buf = bytearray(data)
    count = 0
    i = 0
    while True:
        j = buf.find(old, i)
        if j < 0:
            break
        buf[j : j + len(old)] = rep
        count += 1
        i = j + len(old)
    return bytes(buf), count


def patch_bytes(data: bytes) -> Tuple[bytes, Dict[str, int]]:
    """对 SwiftShader 二进制内容做模式匹配伪装，返回 (新内容, 统计)。"""
    stats: Dict[str, int] = {}
    data, stats["vendorID"] = _replace_keep_length(data, VENDOR_GOOGLE, VENDOR_INTEL)
    data, stats["deviceID"] = _replace_keep_length(data, DEVICE_SWIFTSHADER, DEVICE_INTEL_IRIS)
    for old, new in STRING_PATCHES:
        data, count = _replace_keep_length(data, old, new)
        stats[f"str:{old.decode()}"] = count
    return data, stats


def _has_patchable(data: bytes) -> bool:
    """是否仍存在可伪装的 Google/SwiftShader 特征。"""
    return any(
        pat in data
        for pat in (VENDOR_GOOGLE, DEVICE_SWIFTSHADER, b"SwiftShader Device", b"SwiftShader driver", b"Google")
    )


def find_swiftshader_libs(explicit: Optional[str] = None) -> List[str]:
    """自动定位系统内的 SwiftShader 库；支持显式指定路径。"""
    if explicit:
        return [explicit] if os.path.exists(explicit) else []
    found: List[str] = []
    for pattern in GLOB_PATTERNS:
        found.extend(glob.glob(pattern, recursive=True))
    return sorted(set(found))


def patch_lib(path: str) -> Dict[str, object]:
    """原地 patch 单个库文件，写入前备份为 ``path + .orig``。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception as e:
        return {"path": path, "patched": False, "detail": f"读取失败: {e}"}

    if not _has_patchable(data):
        return {"path": path, "patched": False, "detail": "无待伪装特征（可能已是伪装态或版本不含这些字符串）"}

    new_data, stats = patch_bytes(data)
    if new_data == data:
        return {"path": path, "patched": False, "detail": "patch 未产生任何变化"}

    try:
        shutil.copy2(path, path + ".orig")
        with open(path, "wb") as f:
            f.write(new_data)
        return {"path": path, "patched": True, "detail": f"已伪装 {stats}"}
    except Exception as e:
        return {"path": path, "patched": False, "detail": f"写入失败: {e}"}


def auto_patch(explicit: Optional[str] = None) -> List[Dict[str, object]]:
    """自动定位并伪装所有 SwiftShader 库，返回每个文件的处理结果。"""
    results: List[Dict[str, object]] = []
    for path in find_swiftshader_libs(explicit):
        result = patch_lib(path)
        if result["patched"]:
            logger.info(f"SwiftShader 伪装成功: {path} {result['detail']}")
        else:
            logger.debug(f"SwiftShader 跳过 {path}: {result['detail']}")
        results.append(result)
    return results


def main() -> None:
    """CLI：python -m src.utils.swiftshader_patch [--lib PATH]"""
    import argparse

    parser = argparse.ArgumentParser(description="动态伪装 SwiftShader GPU 特征")
    parser.add_argument("--lib", default=None, help="显式指定 libvk_swiftshader.so 路径")
    args = parser.parse_args()
    results: List[Dict[str, object]] = auto_patch(explicit=args.lib)
    patched: List[Dict[str, object]] = [r for r in results if r["patched"]]
    print(f"处理 {len(results)} 个库，成功伪装 {len(patched)} 个")
    for r in results:
        detail = str(r["detail"])
        mark = "✓ " if r["patched"] else ""
        print(f"  {r['path']}: {mark}{detail}")


if __name__ == "__main__":
    main()
