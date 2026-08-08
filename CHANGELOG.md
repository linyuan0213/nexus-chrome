# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v3.2.4] - 2026-08-08

### 架构重构

- **拆分 `core/session.py`（1031 行）为 `session/` 包**：按职责沿继承链拆分 `base / cookies / fetch / download / media / tabs / session / manager / events`，全部文件 <300 行，消除 Session 上帝类
- **拆分 `core/browser_manager.py`（736 行）为 `browser_manager/` 包**：`env / process / instance / pool / vnc`，导入路径保持兼容
- **`/request` 编排逻辑下沉至 `services/request_service.py`**：挑战判定、响应头清洗、fetch→浏览器网络栈/navigate 回退策略链，`routes.py` 431→324 行
- **拆分 VNC 生命周期**：x11vnc + websockify 进程栈提取为 `vnc.py`（`VncStack`）

### 新功能

- **指纹配置中心**：`/api/profiles` 画像 CRUD、灰度、回滚、HMAC 签名下发、节点心跳
- **WebGL 深度伪装**：画像参数/视口/扩展过滤（`webgl_params`、`webgl_viewport_dims`、`webgl_extensions_remove`）+ 多厂商 persona 预设（Intel/NVIDIA/AMD/Apple）
- **默认指纹环境补桌面典型网络参数**：`FP_NET_RTT=50`、`FP_NET_DOWNLINK=10`

### 修复

- **Docker 构建修复**：sha256 校验文件名不匹配导致构建失败；依赖层/系统层缓存优化；`--no-dev` 镜像瘦身；`TARGETARCH` 默认值移除
- **画像缓存失效**：创建/更新/回滚/灰度后 `invalidate_cache`，避免 TTL 内新会话拿到旧 env
- **httpx 迁移至 httpx2**（starlette TestClient 弃用 httpx）
- **清理过时的 SwiftShader/JS 注入补丁链路**（运行时已切换为 C++ 编译期 patch）
- 移除 noVNC resize 默认值改写与 `--cap-add=SYS_NICE`（新版二进制已关闭 DCHECK，不再需要）

### 其他

- README 同步重构后的架构、完整端点清单与配置说明
- 质量治理：pyright strict 0 错误、ruff 0 错误、159 测试通过

## [Unreleased]

- （待补充）
