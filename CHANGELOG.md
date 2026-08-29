# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v3.2.6] - 2026-08-29

### 修复

- **内嵌 Turnstile 复选框定位兼容新版结构**：新版 Turnstile 的 shadow host 是 `cf-turnstile-response` 输入框的兄弟 div（`wrapper > [div(host), input]`），旧逻辑取输入框父级 shadow root 返回 None，导致签到页复选框找不到、从不点击、Turnstile 一直卡在"人机验证"。现在回退到兄弟 div 的 shadow root，`locate_turnstile_box` 能正确定位并点击复选框

## [v3.2.5] - 2026-08-12

### 修复

- **`CF_WIDGET_FIX_JS` 清空（根治 WebGL 参数覆盖失效）**：旧版 JS monkey-patch 在 `getParameter` 层硬编码 `MAX_VERTEX_ATTRIBS=256`、viewport=32768 等，拦截所有 C++ 层覆盖。清空后 attribs=16、viewport=16384 正常生效
- **指纹配置经命令行开关传递**：Chrome 会剥离渲染/GPU 子进程的环境变量，`FP_*` 无法经 `getenv` 到达 WebGL caps 补丁。改为 `--fp-env-*` 小写开关传递（Chrome 保留开关给所有子进程）
- **vulkan 渲染模式**：headful X11 下 Chrome 默认选的 legacy `--use-angle=swiftshader-webgl` 可被 Google reCAPTCHA 检测（库不初始化）。显式 `--use-angle=vulkan`（SwANGLE）后 reCAPTCHA v3 评分 0.9（human）
- **Managed Challenge 优先于 Turnstile 盒挑战**：托管拦截页误判为盒挑战导致误点超时
- **CI pyright 修复**：pydantic 模型 `__init__` 误报统一处理，pre-commit 与 CI 检查范围对齐

### 新功能

- **画像 WebGL 参数自动生成**：画像未设 `webgl_params` 时按目标平台（macOS/Metal、Windows/D3D11、Linux/Mesa）自动生成自洽能力值，无需手动配置

### 指纹检测（CloakBrowser 基准）

- reCAPTCHA v3：**0.9（human）**
- Cloudflare Turnstile / FingerprintJS / BrowserScan：**全部 PASS**
- incolumitas：1 fail（WEBDRIVER spec，W3C 规范测试）
- TLS 指纹：cipher 哈希与真实 Chrome 一致

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

