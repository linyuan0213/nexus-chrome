# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v3.3.1] - 2026-08-30

### 修复

- **构建失败**：`chrome-cache/` 被 .gitignore 整体忽略，CI/新克隆构建时 `COPY chrome-cache/` 计算 cache key 报 `"/chrome-cache": not found`。改为忽略目录内容、保留 `.gitkeep` 占位，本地包不存在时自动回退 GitHub Releases 下载

## [v3.3.0] - 2026-08-30

### 新增

- **Nexus Chrome Manager 管理前端**（`/ui/`）：Vue 3 + Vite 的可视化管理台，包含概览、会话（导航过盾、截图缩放/下载、标签页、Cookie 管理、点击/拖拽/输入/JS 交互、noVNC 实时画面）、指纹画像（CRUD、版本历史、回滚、灰度发布）、实例监控、事件中心、请求调试台、API Keys 管理、设置页
- **统一认证体系**（设置 `AUTH_PASSWORD` 启用）：登录页签发 24h 短期 session token；第三方程序用 API Key（`ncmk_` 前缀、SHA-256 存储、scope 路径级限权、可吊销）；全局中间件保护 API 与 WebSocket；未设置时保持本地模式不鉴权。新增端点：`POST /api/auth/login|logout`、`GET /api/auth/config|me`、`GET/POST/DELETE /api/auth/keys`
- **实例手动拉起**：`POST /instances/{key}/restart` 主动拉起已停止实例（沿用创建时指纹环境）
- **Cookie 删除**：`DELETE /sessions/{id}/cookies?domain=&name=`（镜像存储级）
- **遗留会话清理**：`DELETE /sessions/recovered` 清空遗留记录
- **平台字体配置**：画像字体/电池/时区环境自洽（`fp/render.py` + `platform_fonts.py`）
- **ruff 内部导入规则**：`TID`（禁相对导入）+ `PLC0415`（禁函数级导入），测试目录豁免

### 修复

- **CF 盒子挑战永不点击**：含 `challenges.cloudflare.com` 脚本的拦截页被误判为托管挑战而干等。改为有可定位 Turnstile 组件（shadow root + iframe 就位）时优先点击复选框
- **复选框坐标偏移**：iframe 内元素 rect 是 iframe 相对坐标，CDP 点击需叠加 iframe 在主页面视口的绝对偏移
- **人性化点击**：复选框点击改贝塞尔轨迹（移动 + 按下/释放）+ ±3px 抖动，最多重试 3 次
- **过盾耗时**：`page.html` 全量读取 6 次 → 1 次（标题快路径）；`tag:iframe` 定位（跨域约 10s）→ `css:iframe`（0.01s）；一次挑战只连接一次跨域帧
- **Xvfb 残留 socket 误判**：容器重启后 `/tmp/.X11-unix/Xn` 残留 + slim 镜像无 pgrep 导致 Xvfb 不启动、Chrome 报 Missing X server。改用 unix socket 连接探测判断存活性
- **websockify 泄漏**：部分死亡重启 / 实例对象替换时旧进程未清理，同端口多进程共享导致 noVNC 能看不能点。VncStack 按端口注册表 + 部分死亡先整体停止
- **截图免导航**：无活跃标签页时自动创建 about:blank 标签页，不再报"没有活跃的标签页"
- **导航自动携带 Cookie**：未显式传 cookie 时自动携带会话内已存储的同域名 Cookie
- **遗留会话注册表膨胀**：记录带 `updated_at`，超 7 天自动过期裁剪
- **nginx**：`/ui/` 静态资源 SPA 回退 + `mime.types`（修复 JS MIME text/plain）

### 变更

- `/status` 移除 VNC 敏感字段（迁至认证后的 `GET /api/auth/me`）
- 遗留会话提示条新增"清除遗留记录"按钮

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

