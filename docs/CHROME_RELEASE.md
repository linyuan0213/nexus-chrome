# Patched Chromium 构建发布 SOP（153 → 155 之后）

端到端流程：**chromefp 构建** → **GitHub 发布** → **冒烟** → **nexus-chrome 版本切换/发版**。
涉及两个工程：
- **chromefp**（独立，本机 `~/python/chromefp`，构建机 `~/chromefp`）：单版本跟随的 patched Chromium 构建工程（patch/core-files/MANIFEST/build/remote）。
- **nexus-chrome**（本仓库）：消费 chrome-<ver> 二进制的服务镜像。

---

## 0. 关键位置（构建机 54.39.16.207, 用户 debian）

```
~/chromefp               # 工程代码（补丁集/构建脚本/cfp CLI）
~/chromefp-src/
├─ work/src              # 当前受支持版本源码（含 .gn/.gclient；现为 155.0.8044.0）
└─ ccache/               # 统一 ccache（跨架构/版本共享）
~/archive/               # 退役源码树 / 历史工具归档
```
本机 nexus-chrome：`chrome-cache/` 放构建产物 tar（镜像构建优先使用，否则回退 GitHub 下载）。

## 1. 日常/增量构建（不换版本）

```bash
# 在 chromefp 本地执行；远端默认走 ~/chromefp
./remote.sh sync                                  # 同步补丁集到构建机
CHROMEFP_SRC=/home/debian/chromefp-src/work/src ./remote.sh build x64 155.0.8044.0   # 或 arm64/both
./remote.sh status / watch
```
产物：`~/chromefp/dist/chrome-<ver>-<arch>.tar.gz` + `.sha256`。
> 首次构建某架构需全量编译（数小时）；同版本二次构建走 out 增量 + ccache。

## 2. 发布到 GitHub（nexus-chrome-bin）

```bash
# 在构建机（gh 已登录 linyuan0213）
cd ~/chromefp/dist
gh release create chrome-<ver> chrome-<ver>-x64.tar.gz chrome-<ver>-x64.tar.gz.sha256 \
   --repo linyuan0213/nexus-chrome-bin --title "Chrome <ver> (patched)"
# 追加补传另一架构：
gh release upload chrome-<ver> chrome-<ver>-arm64.tar.gz chrome-<ver>-arm64.tar.gz.sha256 \
   --repo linyuan0213/nexus-chrome-bin --clobber
```
Release tag 名 = `chrome-<ver>`（镜像下载 URL 依据）。

## 3. 冒烟（先旁路栈，后生产）

```bash
# 旁路验证（不打扰 9850 生产）：compose.155.yml 模板已入库
mkdir -p data155 && cp data/fp_config_center.db data155/
docker compose -f docker-compose.yml -f compose.155.yml up -d --build   # 端口 9860
# 冒烟矩阵：deviceandbrowserinfo.com/are_you_a_bot isBot=false
#           javlibrary / ourbits / pterclub 过 CF（mac/windows/linux 身份）
# 通过后清场：docker rm -f nexus-chrome-155；删除 data155
```

## 4. 生产版本切换（nexus-chrome）

```bash
# 单一事实源 .chrome-version + 自动派生（settings UA 兜底 / 镜像 ENV）
./scripts/set-chrome-version.sh <ver>
# 产物放本地 chrome-cache（镜像构建优先用，避免依赖 GitHub 下载）
docker compose up -d --build
# 验证：/status 正常；docker exec nexus-chrome /opt/patched-chrome/chrome --version
```

## 5. 升级到新 Chromium 版本（153→155 已验证的完整路径）

见 **chromefp/DESIGN.md** 单版本迁移 8 步，关键命令：
```bash
./cfp check --src=<新源码树>        # 找失效补丁
./cfp rebase <patch> --old=<旧树> --new=<新树>   # 生成变体（人工 review）
# 构建/冒烟/发布后回 nexus-chrome 执行第 4 步
```
chromefp 侧以 git tag（`chrome-<旧ver>`/`chrome-<新ver>`）留存可回滚快照（本地仓库，未推 GitHub）。

## 6. 回滚

- 二进制：nexus-chrome 切回上一版本号 + 本地 `chrome-cache/` 旧 tar（未覆盖的话）或 GitHub 旧 release asset
- 补丁集：chromefp `git checkout chrome-<旧ver> -- patches/ MANIFEST.yaml core-files/` 再构建
- 身份 UA：画像级 UA 声明在指纹配置中心（DB），与二进制版本解耦，升级不自动改；如需对齐手动更新画像

## 当前状态（2026-09-06）

- 受支持版本：**155.0.8044.0**（x64 已构建+发布+生产切换通过；arm64 构建进行中）
- chromefp tags：`chrome-153.0.7991.0`（回滚）/ `chrome-155.0.8044.0`
- nexus-chrome dev 领先 origin 的提交集待按 dev→release→master 发版
