#!/bin/bash
# set-chrome-version.sh — Chrome 版本升级入口（nexus-chrome 侧，唯一手工点）
#
# 配合 chromefp（独立工程）完成二进制构建/发布后，在此仓库一条命令对齐所有引用：
#   .chrome-version  Dockerfile ARG  docker-compose CHROME_VERSION  DESIGN.md 表
#
# 用法: ./scripts/set-chrome-version.sh 155.0.8044.0
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="${1:-}"
if ! echo "$VER" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "用法: $0 <完整版本号>  例: $0 155.0.8044.0"; exit 1
fi
MAJOR="${VER%%.*}"

cd "$ROOT"

# 1) 运行时单一事实源
printf '%s\n' "$VER" > .chrome-version

# 2) Dockerfile ARG 默认值（裸 docker build 兜底）
sed -i -E "s/^(ARG CHROME_VERSION=).*/\1${VER}/" Dockerfile

# 3) docker-compose 构建参数（保留 ${CHROME_VERSION:-...} 环境覆盖）
sed -i -E "s/^([[:space:]]*CHROME_VERSION: )\"[^\"]*\"/\1\"\${CHROME_VERSION:-$VER}\"/" docker-compose.yml

# 4) DESIGN.md 环境变量表
sed -i -E "s/(\`CHROME_VERSION\` \| )\`[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\`/\1\`${VER}\`/" DESIGN.md

echo "==> Chrome 版本已切换至 $VER"
echo "    引用核对（应各 1 处 155/当前）："
grep -n "^${VER}\$" .chrome-version
grep -n "ARG CHROME_VERSION=${VER}" Dockerfile
grep -n "CHROME_VERSION: .*${VER}" docker-compose.yml
grep -n "CHROME_VERSION.*${VER}" DESIGN.md
echo "==> 提示：settings.py UA 兜底由 .chrome-version/镜像 ENV 自动派生，无需再改"
