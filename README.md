# Nexus Chrome 服务器

基于 patched Chromium（C++ 编译期指纹）的挑战绕过、Cookie 提取与指纹仿真服务。

## 项目结构

```
nexus-chrome/
├── src/                        # 源代码
│   ├── main.py                # 主 FastAPI 应用（装配、生命周期、/instances、/ws/events）
│   ├── config/                # 配置模块
│   │   ├── settings.py        # 应用设置和常量
│   │   └── scripts.py         # 浏览器 JS 脚本（Turnstile 组件修复等）
│   ├── core/                  # 核心业务
│   │   ├── browser_manager/   # 浏览器实例池（包）
│   │   │   ├── env.py         #   时区检测与基础 FP_* 环境
│   │   │   ├── process.py     #   Chrome 启动参数、端口/Xvfb 原语
│   │   │   ├── instance.py    #   ChromeInstance 单实例生命周期
│   │   │   └── pool.py        #   BrowserPool 实例池与监控回收
│   │   ├── session/           # 会话（包，按职责沿继承链拆分）
│   │   │   ├── base.py        #   属性声明与标签页/指纹底层原语
│   │   │   ├── cookies.py     #   Cookie 存取与合并
│   │   │   ├── fetch.py       #   浏览器网络栈请求（自动过盾）
│   │   │   ├── download.py    #   文件下载（原生 + JS fetch 回退）
│   │   │   ├── media.py       #   m3u8 探测与解析
│   │   │   ├── tabs.py        #   标签页管理与截图
│   │   │   ├── session.py     #   核心：导航过盾、页面交互、代理
│   │   │   ├── manager.py     #   SessionManager 与持久化注册表
│   │   │   └── events.py      #   全局事件总线（WebSocket 推送）
│   │   ├── cookie_store.py    # Cookie 共享存储
│   │   └── fingerprint.py     # 指纹管理器
│   ├── challenge/             # 挑战解析器（策略模式）
│   │   ├── resolver.py        #   编排器
│   │   ├── cloudflare.py / five_second_shield.py / leichi.py / generic.py
│   ├── fp/                    # 指纹画像（配置中心客户端）
│   │   ├── profile.py / store.py / render.py / service.py
│   │   └── sync_client.py / signing.py / config.py
│   ├── services/              # 应用编排层（api → services → core/fp）
│   │   ├── session_service.py #   会话创建：画像解析 → 实例路由 → 会话
│   │   └── request_service.py #   /request 聚合请求（fetch→过盾回退策略链）
│   ├── http/                  # HTTP 客户端（httpx2，与 CookieStore 双向同步）
│   ├── api/                   # API 层
│   │   ├── routes.py          #   /sessions 会话路由（薄处理器）
│   │   ├── fp_profiles.py     #   /api/profiles 画像 CRUD 路由
│   │   └── schemas.py         #   请求/响应模型
│   └── utils/                 # 工具函数
│       ├── challenge_utils.py / cleanup.py / humanize.py
├── main.py                    # 应用入口点
├── tests/                     # pytest 测试套件
├── docs/                      # 文档（指纹配置中心 API）
├── examples/                  # 画像示例
├── deploy/                    # nginx 配置
├── scripts/                   # 辅助脚本（本地 CDP Chrome、字体配置）
├── pyproject.toml             # 项目配置和依赖管理（uv）
├── Dockerfile                 # Docker 配置（下载 patched Chromium）
├── supervisord.conf           # 进程管理
└── start.sh                   # 启动脚本
```

## 功能特性

- **多指纹并发**：每个指纹画像对应独立 Chrome 进程（独立 user-data-dir / 调试端口 / `FP_*` 环境变量），不同指纹同时运行
- **C++ 级指纹**：指纹编译进 patched Chromium 二进制（`fp_config` 读 `FP_*` 环境变量），非 JS 注入，避免被风控检测
- **网络层一致性**：HTTP 请求头（User-Agent / Sec-CH-UA）与 JS 指纹同步覆盖
- **自动过盾**：Cloudflare（标准/Turnstile 嵌入）、五秒盾、雷池、通用 WAF、ALTCHA
- **Cookie 共享**：浏览器过盾后自动复用 Cookie 到 HTTP 快路径
- **人性化交互**：贝塞尔轨迹点击/拖拽，对抗鼠标轨迹检测
- **指纹配置中心**：画像 CRUD / 灰度 / 回滚 / HMAC 签名下发
- **RESTful API + WebSocket 事件推送**
- **网页 VNC**：通过 noVNC 查看浏览器会话（容器模式）

## API 端点

### 根路径与实例
- `GET /` - API 信息
- `GET /status` - 服务状态
- `GET /instances` - 列出浏览器实例
- `POST /instances/{key}/restart` - 手动拉起已停止的实例
- `DELETE /instances/{key}` - 手动关闭实例
- `WS /ws/events?types=...` - 事件推送（session_created / session_deleted；认证开启时 query 带 `Authorization=Bearer <token>`）

### 认证（设置 `AUTH_PASSWORD` 后启用）
- `POST /api/auth/login` - 登录（密码 → 24h 短期 session token）
- `POST /api/auth/logout` - 登出
- `GET /api/auth/config` - 认证是否开启（公开，前端探测用）
- `GET /api/auth/me` - 认证状态 + VNC 密码等安全配置（需认证）
- `GET/POST /api/auth/keys`、`DELETE /api/auth/keys/{id}` - API Key 管理（第三方程序凭证，`ncmk_` 前缀，scope 路径级限权，可吊销）

### 管理后台（Web UI）
- `GET /ui/` - Nexus Chrome Manager（会话/画像/实例/事件/调试台/API Keys 可视化管理；构建自 `frontend/`）

### Session 管理
- `POST /sessions` - 创建会话（支持 `fp_profile_id` 绑定指纹画像）
- `GET /sessions` - 列出会话（含可恢复会话）
- `DELETE /sessions/{id}` - 删除会话
- `DELETE /sessions/recovered` - 清空遗留会话记录（遗留记录超 7 天自动过期）

### 浏览器操作（基于 Session）
- `POST /sessions/{id}/navigate` - 浏览器导航（自动过盾、提取 Cookie）
- `GET /sessions/{id}/html` - 获取当前页面 HTML
- `GET /sessions/{id}/cookies` - 获取已存储 Cookie
- `DELETE /sessions/{id}/cookies?domain=&name=` - 删除单个 Cookie（镜像存储级）
- `POST /sessions/{id}/click` - 点击元素（人性化轨迹）
- `POST /sessions/{id}/drag` - 拖拽（滑块验证码）
- `POST /sessions/{id}/input` - 输入文本
- `POST /sessions/{id}/execute` - 执行自定义 JavaScript
- `POST /sessions/{id}/screenshot` - 截图（base64 PNG）
- `POST /sessions/{id}/proxy` - 运行时切换代理

### 标签页
- `GET /sessions/{id}/tabs` - 列出标签页
- `POST /sessions/{id}/tabs` - 新建标签页
- `POST /sessions/{id}/tabs/switch` - 切换活动标签页
- `DELETE /sessions/{id}/tabs/{tab_name}` - 关闭标签页

### HTTP 请求
- `POST /sessions/{id}/fetch` - 纯 HTTP 请求（复用 Session Cookie）
- `POST /sessions/{id}/request` - 聚合请求（fetch 优先，命中挑战自动过盾回退）
- `POST /sessions/{id}/download` - 浏览器网络栈下载
- `POST /sessions/{id}/m3u8` - m3u8 播放列表探测与解析

### 指纹配置中心
- `GET/POST /api/profiles` - 画像列表 / 创建更新
- `GET /api/profiles/{id}` - 画像详情（节点拉取，HMAC 签名）
- `GET /api/profiles/{id}/versions` - 历史版本
- `POST /api/profiles/{id}/rollback` - 回滚
- `POST /api/profiles/{id}/gray` - 灰度发布
- `GET /api/nodes/{node_id}/heartbeat` - 节点心跳

完整画像 API 见 `docs/fp_config_center_api.md`。

## 安装部署

### 直接安装

1. 克隆仓库：
```bash
git clone https://github.com/linyuan0213/nexus-chrome.git
cd nexus-chrome
```

2. 使用 uv 安装依赖：
```bash
uv sync
```

3. 运行服务器：
```bash
uv run python main.py
```

### Docker 部署

镜像构建时自动从 GitHub Releases 下载 patched Chromium（版本由 `.chrome-version` 锁定）。

推荐使用仓库内 `docker-compose.yml` 一键部署（构建 + 数据卷 + 共享内存 + 端口）：

```bash
docker compose up -d --build
```

或在 Nexus Media 侧以服务编排方式部署，之后在 **系统设置 → 实验室** 配置：

```yaml
laboratory:
  chrome_enabled: true
  chrome_server_host: "http://<本机IP>:9850"   # 填 nexus-chrome 所在主机
```

Agent 的 `browser_fetch` / `browser_screenshot` 工具即调用该服务；首次使用请在浏览器自动化页面登录站点并同步指纹，之后工具可携带站点 Cookie 访问登录后页面。

手动部署：

1. 构建镜像：
```bash
docker build -t nexus-chrome-novnc .
```

2. 运行容器（nginx 统一入口 9850 + VNC 端口范围）：

```bash
docker run --shm-size=2g \
  -e VNC_PASSWORD=your_password \
  -p 9850:9850 \
  -p 5900-5910:5900-5910 \
  -p 6080-6100:6080-6100 \
  -d nexus-chrome-novnc
```

### 网页 VNC 访问

**统一入口（推荐）：nginx 在 9850 端口**，按实例路径路由，无需记端口号：

```bash
# 浏览器直接访问该实例的 noVNC（display :N 对应 /chromeN/，默认实例=1）
http://<host>:9850/chrome1/     # display :1 的实例（默认实例）
http://<host>:9850/chrome2/     # display :2 的实例
```

- `/chromeN/` → 该实例的 websockify（noVNC 页面 + VNC 隧道）
- `/`（及 `/sessions`、`/instances` 等 API）→ FastAPI 应用（内部 9851）

`GET /instances` 返回每个实例的 `display`（即 `/chrome{display号}/`）与 `web_port`。

**备用：直连 websockify 端口**（端口已发布到宿主机）：

```bash
http://<host>:6081/   # display :1 的 noVNC
```

**端口说明：**
- `9850`: **nginx 统一入口**（实例 noVNC `/chromeN/` + 应用 API `/`）
- `5900+N`: 每实例 x11vnc（`display :N`，仅容器内 127.0.0.1）
- `6080+N`: 每实例 websockify（nginx 上游，也可直连）

## 使用示例

### 创建会话并导航（自动过盾）

```bash
# 创建会话（可选 fp_profile_id 绑定指纹画像）
curl -X POST http://localhost:9850/sessions \
  -H "Content-Type: application/json" \
  -d '{"session_id": "work", "fingerprint_profile": "stealth"}'

# 导航并自动过盾，Cookie 自动入库
curl -X POST http://localhost:9850/sessions/work/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://protected-site.com", "timeout": 60}'

# 后续 HTTP 请求复用 Cookie
curl -X POST http://localhost:9850/sessions/work/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "https://protected-site.com/api/search?q=test"}'
```

### 指纹画像

创建画像后，会话绑定 `fp_profile_id` 即注入完整指纹（UA / platform / WebGL / cores / 时区等）。

```bash
# 创建 macOS 自洽画像（WebGL 参数自动按平台生成）
curl -X POST http://localhost:9850/api/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "profile_id": "mac_work",
    "name": "macOS 自洽指纹",
    "fingerprint": {
      "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
      "platform": "MacIntel",
      "uad_platform": "macOS",
      "webgl_vendor": "Google Inc. (Apple)",
      "webgl_renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
      "cores": 4,
      "memory": 8.0
    }
  }'

# 用画像创建会话
curl -X POST http://localhost:9850/sessions \
  -H "Content-Type: application/json" \
  -d '{"session_id": "mac", "fp_profile_id": "mac_work"}'
```

画像未显式设置 `webgl_params` 时，服务端按目标平台自动生成自洽的 WebGL 能力值（`MAX_VERTEX_ATTRIBS=16`、`MAX_ELEMENT_INDEX=4294967294`、viewport 按平台等），无需手动配置。显式设置优先。

> 注意：画像的 `cores` 应与宿主机实际核数一致（可被实测并行度戳穿），UA 版本应与浏览器二进制版本一致（避免 HTTP 头与 JS 版本不一致）。

### 交互操作（签到等）

```bash
# 输入文本
curl -X POST http://localhost:9850/sessions/work/input \
  -H "Content-Type: application/json" \
  -d '{"selector": "#username", "text": "admin"}'

# 人性化点击元素
curl -X POST http://localhost:9850/sessions/work/click \
  -H "Content-Type: application/json" \
  -d '{"selector": "#submit"}'
```

## 指纹测试结果

针对 CloakBrowser 基准的 10 项在线检测，当前构建（vulkan 渲染 + C++ 编译期指纹）实测结果与 CloakBrowser 同级：

| 检测项 | Stock Playwright | CloakBrowser | **Nexus Chrome** |
|---|---|---|---|
| reCAPTCHA v3 | 0.1 (bot) | 0.9 (human) | **0.9 (human)** ✓ |
| Cloudflare Turnstile (managed) | FAIL | PASS | **PASS**（javlibrary ~2s） |
| FingerprintJS bot detection | DETECTED | PASS | **PASS**（`bot: not_detected`） |
| BrowserScan bot detection | DETECTED | NORMAL | **NoDetection**，真实性 90% |
| bot.incolumitas.com | 13 fails | 1 fail | **1 fail**（WEBDRIVER spec） |
| navigator.webdriver | true | false | **false** |
| navigator.plugins.length | 0 | 5 | **5** |
| window.chrome | undefined | object | **object** |
| UA 字符串 | HeadlessChrome | Chrome | **Chrome/153 无泄漏** |
| CDP 检测 | Detected | Not detected | **cdc_ 未定义** |
| TLS 指纹 | Mismatch | 与 Chrome 一致 | **cipher 哈希与 Chrome 一致** |

### 说明

- **incolumitas 的 1 个 fail 是 W3C WebDriver 规范测试**（`WEBDRIVER`），连 CloakBrowser 都过不了，属预期
- BrowserScan 90% 中 -10% 为 SwiftShader 软渲染 vs 声称 GPU 的固有差距（WebGL exception / vendors vary），需真实 Apple/GPU 硬件才能到 100%
- 可配置项：`canvas_noise` / `audio_noise` 保持 `false`（开启会被 BrowserScan 标记为"函数被修改"，-15%）

### 复测方式

```bash
# 建会话绑定画像后依次导航检测站，用 execute 提取结果
curl -X POST http://localhost:9850/sessions -d '{"session_id":"t","fp_profile_id":"mac_work"}'
curl -X POST http://localhost:9850/sessions/t/navigate \
  -d '{"url":"https://demo.fingerprint.com/playground","timeout":40}'   # FingerprintJS
curl -X POST http://localhost:9850/sessions/t/navigate \
  -d '{"url":"https://browserscan.net/","timeout":40}'                  # BrowserScan
curl -X POST http://localhost:9850/sessions/t/navigate \
  -d '{"url":"https://bot.incolumitas.com/","timeout":40}'              # incolumitas
curl -X POST http://localhost:9850/sessions/t/navigate \
  -d '{"url":"https://www.javlibrary.com/tw/","timeout":60}'            # Cloudflare managed
```

reCAPTCHA v3 评分验证：在 `recaptcha-demo.appspot.com/recaptcha-v3-request-scores.php` 页执行 `grecaptcha.enterprise.execute` 取 token，POST 至 `/recaptcha-v3-verify.php?action=examples/v3scores&token=...`，响应 `score` 字段即评分（实测 0.9）。

## 配置

环境变量：
- `APP_HOST`: 服务器主机（默认：0.0.0.0）
- `APP_PORT`: 服务器端口（默认：9850）
- `CHROME_PATH`: 自定义 Chrome 浏览器路径（容器内默认 `/opt/patched-chrome/chrome`）
- `HEADLESS_MODE`: 无头模式（默认：`--headless=new`）
- `CHROME_RENDER_MODE`: 渲染后端（`vulkan` / `swiftshader` / `auto`）。**推荐 `vulkan`**（SwiftShader 软件 Vulkan/SwANGLE）：headful X11 下 Chrome 默认选的 legacy `swiftshader-webgl` 可被 Google reCAPTCHA 等检测，显式 `vulkan` 后指纹真实且过检测
- `VK_ICD_FILENAMES`: SwiftShader Vulkan ICD 路径（vulkan 模式需指向 `/opt/patched-chrome/vk_swiftshader_icd.json`）
- `REMOTE_CHROME_ADDRESS`: 远程 Chrome CDP 地址，如 `127.0.0.1:9222`
- `VNC_PASSWORD`: VNC 密码（部署时必须修改，禁止默认值）
- `AUTH_PASSWORD`: 管理后台访问密码。设置后启用登录页 + 全 API/WS 鉴权（人机分离：用户登录签发 24h 短期 token，第三方程序用 API Key）；**未设置则认证完全关闭（本地模式）**
- `CHALLENGE_TIMEOUT`: 挑战等待超时（默认：60 秒）
- `HTTP_CLIENT_TIMEOUT`: HTTP 客户端超时（默认：30 秒）
- `MAX_BROWSERS`: 浏览器实例上限（默认：5）
- `INSTANCE_IDLE_TTL`: 空闲实例回收 TTL（默认：600 秒）
- `DATA_DIR`: 会话持久化目录（默认：`./data`）
- `USER_DATA_PATH`: Chrome 用户数据目录路径（默认：`~/.cache/nexus-chrome/user_data`）
- `PROFILE_DATA_DIR`: 画像实例用户数据目录（默认：`~/.cache/nexus-chrome/profiles`）
- `FP_ADMIN_TOKEN` / `FP_NODE_TOKEN`: 配置中心鉴权（设置后强制校验；统一认证开启时 session token / scope=profiles 的 API Key 也可访问）
- `CLEANUP_ENABLED`: 是否启用用户数据目录定期清理（默认：`true`）
- `CLEANUP_INTERVAL`: 清理间隔，单位秒（默认：3600）
- `CLEANUP_MAX_SIZE_GB`: 超过该大小触发深度清理，单位 GB（默认：2，0 表示禁用）
- `CLEANUP_MAX_AGE_SECONDS`: 仅删除超过该秒数的文件/目录（默认：0，表示不限制）
- `CLEANUP_KEEP_COOKIES`: 清理时是否保留 Cookies 文件（默认：`true`）

### 防止 `DeferredBrowserMetrics` 等目录无限增长

Chrome 的 `--user-data-dir` 会不断写入缓存、IndexedDB、Local Storage、Metrics 等文件。如果你把该目录映射到宿主机（如 `-v /data:/data`），长期运行后可能出现 `DeferredBrowserMetrics` 目录占满磁盘。

本项目内置了一个后台清理任务，配合以下环境变量工作：

- **启动时清理**：服务启动前会清理一次缓存和 metrics 文件。
- **后台定期清理**：`CLEANUP_ENABLED=true` 时，按 `CLEANUP_INTERVAL` 周期运行。
- **阈值深度清理**：当目录超过 `CLEANUP_MAX_SIZE_GB` 时，触发深度清理，删除 `IndexedDB`、`Local Storage`、`Session Storage` 等。
- **Chrome 启动参数优化**：限制磁盘缓存大小、关闭崩溃报告和组件自动更新等。

推荐无持久化需求的 Docker 部署（数据在容器内，重启后自动清空）：

```bash
docker run --shm-size=2g \
  -e VNC_PASSWORD=your_password \
  -e USER_DATA_PATH=/tmp/nexus-chrome/user_data \
  -e CLEANUP_ENABLED=true \
  -e CLEANUP_MAX_SIZE_GB=2 \
  -p 9850:9850 -p 6080:6080 \
  -d nexus-chrome-novnc
```

如果你必须持久化用户数据到宿主机，只要保持 `CLEANUP_ENABLED=true`，后台任务会自动控制目录大小。

## 开发

### 运行测试

```bash
uv run pytest tests/ -v
```

### 质量检查

```bash
uv run ruff check src tests main.py   # lint
uv run pyright src                    # 类型检查（strict）
```

pre-commit 已配置 ruff + ruff-format + pyright 钩子。

### 代码结构

分层架构：`api → services → {core, fp, challenge, http}`

- **src/api**: 薄路由层，只做参数校验与响应包装
- **src/services**: 应用编排（唯一同时依赖 core 与 fp 的层，打破 core↔fp 纠缠）
- **src/core**: 会话与浏览器池（不感知 fp 层）；session 与 browser_manager 均为按职责拆分的包
- **src/fp**: 指纹画像（模型/SQLite 存储/渲染/远程同步/HMAC 签名）
- **src/challenge**: 挑战解析器（策略模式，Cloudflare/五秒盾/雷池/通用）
- **src/http**: 基于 httpx2 的 HTTP 客户端，与 Session Cookie 双向同步
- **src/config**: 配置与常量（JS 脚本独立在 scripts.py）

## 指纹配置中心（内建）

nexus-chrome 内建指纹画像管理（`/api/profiles`），配合 patched Chromium 的原生指纹读取：

- **画像管理**：`GET/POST /api/profiles`、回滚、灰度、历史版本
- **签名下发**：HMAC-SHA256，节点验签后使用
- **节点心跳**：`GET /api/nodes/{node_id}/heartbeat`
- **浏览器接线**：会话创建传 `fp_profile_id` → 解析画像 → 注入 `FP_*` 环境变量 → 按画像启动浏览器（画像变化自动重启）
- **客户端**：`src/fp/`（模型/渲染/sync/存储）

完整 API 见 `docs/fp_config_center_api.md`。鉴权：设置 `FP_ADMIN_TOKEN`/`FP_NODE_TOKEN` 环境变量即强制校验。

## 许可证

MIT License - 详见 LICENSE 文件。
