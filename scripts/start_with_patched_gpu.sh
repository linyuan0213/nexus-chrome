#!/bin/bash
# 如果已执行 --in-place patch，直接启动即可。
# 如果未 patch，用 unshare bind mount 注入。
# 用法: bash scripts/start_with_patched_gpu.sh

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCHED="$PROJECT_ROOT/patched_libs/libvk_swiftshader.so"
ORIGINAL="/opt/google/chrome/libvk_swiftshader.so"

strings "$ORIGINAL" | grep -q "Intel Iris Pro" 2>/dev/null && {
    echo "SwiftShader 已 patch (in-place)，直接启动"
    exec uv run python main.py
}

if [ -f "$PATCHED" ]; then
    echo "使用 unshare bind mount 注入 patched 库..."
    exec unshare -rm bash -c "
        mount --bind '$PATCHED' '$ORIGINAL' &&
        exec uv run python main.py
    "
else
    echo "先运行: python3 scripts/patch_swiftshader.py"
    exit 1
fi
