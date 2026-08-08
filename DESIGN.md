# Nexus Chrome Server - 架构设计文档

## 概述

基于 patched Chromium 的挑战绕过、Cookie 提取与指纹仿真服务器。核心能力：

- **多指纹并发**：每个指纹画像对应一个独立 Chrome 实例（进程级隔离），不同指纹可同时运行
- **C++ 级指纹**：指纹通过编译进二进制的 `fp_config`（FP_* 环境变量）实现，非 JS 注入（JS 注入与像素噪声可被风控检测）
- **网络层一致性**：HTTP 请求头（User-Agent / Sec-CH-UA）与 JS 指纹同步覆盖，杜绝"JS 说 151、请求头说 153"的泄漏
- **挑战编排**：策略模式多类型 WAF（Cloudflare 标准/Turnstile 嵌入、五秒盾、雷池、通用、ALTCHA 工作量证明）
- **指纹配置中心**：画像 CRUD / 灰度 / 回滚 / HMAC 签名下发，支持 nexus-media 前端注入真实浏览器指纹

## 核心概念

### 指纹实例（ChromeInstance）与实例池（BrowserPool）

**关键约束**：patched Chromium 的 `fp_config` 通过 `getenv` 读取指纹参数，**指纹是进程级**的。
因此不同指纹必须运行在**独立 Chrome 进程**中，无法在同一进程内切换。

```
┌──────────────────────────────────────────────────────────────┐
│                        BrowserPool                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐  │
│  │ default 实例      │  │ user_42 实例      │  │ site-a 实例  │  │
│  │ port=9222        │  │ port=9223        │  │ port=9224   │  │
│  │ user_data=…/default│ │ user_data=…/user_42│ │ …/site-a    │  │
│  │ FP_*=base        │  │ FP_*=画像42       │  │ FP_*=画像a  │  │
│  └──────────────────┘  └──────────────────┘  └─────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

每个实例拥有：
- **独立 user-data-dir**：Cookie / localStorage / 缓存完全隔离
- **独立调试端口**：DrissionPage 独立连接
- **独立 FP_\* 环境变量**：指纹差异化
- **实例级生命周期**：惰性启动、监控重启、超限回收（`MAX_BROWSERS`）

### 会话（Session）与实例路由

```
POST /sessions {"session_id":"s1", "fp_profile_id":"user_42"}
  └─ resolve_profile_env(user_42) → FP_* env
     └─ pool.get("user_42", env) → 该画像的 ChromeInstance
        └─ Session 绑定该实例的 Chromium
```

- 同一 `fp_profile_id` 的会话 **共享**一个实例（指纹一致、Cookie 互通）
- 不同 `fp_profile_id` 的会话 **完全隔离**
- 无 `fp_profile_id` → 默认实例

### 指纹体系（C++ 级，非 JS 注入）

**为什么不用 JS 注入**：`Page.addScriptToEvaluateOnNewDocument` 注入的脚本可被
`Function.prototype.toString`、属性描述符等检测；Canvas/Audio **像素噪声被检测为
"篡改"**（真实浏览器渲染是确定性的）；macOS 风格 WebGL 字符串安在 Linux 上自相矛盾。

**正确方案**：指纹参数编译进二进制（`fp_config.h` 读 `FP_*` env，Blink/网络层 patch），
运行时由进程环境变量控制：

| 层级 | 实现 | 覆盖范围 |
|---|---|---|
| Blink 渲染层（JS 可见）| `fp_config.h` 内联 + C++ patch | userAgentData、platform、WebGL getParameter、canvas/audio、screen |
| 网络层（HTTP 请求头）| `Network.setUserAgentOverride` 动态覆盖 | User-Agent、Sec-CH-UA\* 系列头 |
| 二进制层 | `libvk_swiftshader` 等 | 底层渲染字符串 |

**网络层一致性（关键）**：fp_config 只 patch Blink 层，HTTP 请求头若不同步会泄漏
真实版本（如 JS 说 151、请求头说 153），被严格风控直接判定。`_apply_ua_metadata`
按画像动态设置 `Network.setUserAgentOverride`（含 brands/fullVersionList），使
请求头与 JS 指纹完全一致。

**screen 一致性**：注入的 `FP_SCREEN_WIDTH/HEIGHT` 必须与窗口/显示实际尺寸一致，
否则 `screen.width=2560` 而 `availWidth=1366` 会被判定为修改。默认使用
`WINDOW_SIZE` 统一的窗口与显示。

### 指纹画像（fp_profile）

画像通过 `POST /api/profiles` 管理（见 `docs/fp_config_center_api.md`），
`fingerprint` 字段映射为 `FP_*` env（`src/fp/render.py`）。支持：

- **CRUD + 版本**：每次更新 version +1，可回滚
- **灰度**：按节点哈希百分百 / 显式节点列表
- **HMAC 签名**：节点拉取时验签（`FP_CENTER_SECRET`）
- **多节点**：本地 SQLite 为主，远程配置中心可选回退

**nexus-media 集成**：前端采集用户真实浏览器指纹（UA/userAgentData/WebGL 字符串/
screen/硬件/语言）→ 后端按用户映射 `user_<id>` 画像 → nexus-chrome 会话以
`fp_profile_id` 使用。注意：**渲染类指纹（canvas/WebGL 像素）无法注入**，仅字符串层。

### 挑战编排（ChallengeOrchestrator）

策略模式，四阶段流水线：

```
detect → identify → resolve → verify
  │
  ├─ CloudflareResolver：标准挑战 + Turnstile 嵌入（solve_embedded_widget）
  ├─ FiveSecondShieldResolver：五秒盾
  ├─ LeichiResolver：雷池
  ├─ GenericResolver：通用 WAF
  └─ ALTCHA：工作量证明（点击复选框 → 浏览器内计算 PoW → altchaPayload 填充）
```

嵌入 Turnstile（业务页内 "请验证您是真人"）与全页挑战分开处理：
- 全页挑战：检测拦截页 → 逐层解决 → 等跳转
- 嵌入组件：`cf-turnstile-response` token 生成 + shadow DOM 复选框点击

### 环境边界（已知限制）

- **无 GPU**：运行在无 GPU 虚拟机（bochs 帧缓冲），WebGL/Canvas 为 swiftshader
  软件渲染。宽松 Turnstile（如 javlibrary）可通过；**严格 Turnstile（如 audiences.me，
  校验渲染输出）无法通过**，字符串指纹无法改变渲染。
- **TLS 指纹**：patched chromium 的 JA3/JA4 与真实 Chrome 不同，无法注入。
- 解决路径：VM 配 virtio-gpu 3D 加速（宿主层）或 TLS 栈 patch（C++ 网络层）。

## 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                        FastAPI (src/main.py)                  │
├──────────────────────────────────────────────────────────────┤
│  API 层 (src/api/)                                            │
│  /sessions*  /api/profiles*  /instances  /status             │
├──────────────────────────────────────────────────────────────┤
│  核心层 (src/core/)                                           │
│  ┌────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  BrowserPool   │  │ SessionManager    │  │ CookieStore  │   │
│  │  ChromeInstance│  │ 会话→实例路由      │  │ 域名→Cookie  │   │
│  │  (多进程实例)   │  │ 标签页池管理      │  │ 会话隔离      │   │
│  └────────────────┘  └──────────────────┘  └──────────────┘   │
├──────────────────────────────────────────────────────────────┤
│  指纹层 (src/fp/)                                             │
│  profile模型 / render(FP_* env) / store(SQLite) / service      │
│  sync_client(远程+验签) / signing(HMAC) / fp_profiles API      │
├──────────────────────────────────────────────────────────────┤
│  挑战层 (src/challenge/)                                       │
│  Orchestrator → Cloudflare / 五秒盾 / 雷池 / 通用 / ALTCHA     │
├──────────────────────────────────────────────────────────────┤
│  HTTP 层 (src/http/) / 配置层 (src/config/)                    │
└──────────────────────────────────────────────────────────────┘
```

## 数据流

### 创建会话并绑定指纹

```
POST /sessions {"session_id":"s1","fp_profile_id":"user_42"}
  ├─ resolve_profile_env("user_42") → FP_* env（SQLite 画像 → render_env）
  ├─ pool.get("user_42", env) → ChromeInstance
  │   ├─ 首次：分配端口 + user_data_dir + 启动 chrome（注入 FP_* env）
  │   └─ 已存在：复用
  ├─ inst.ensure() → DrissionPage Chromium
  └─ Session(browser=该实例 Chromium, fp_profile_id="user_42")
```

### 导航 + 过挑战 + Cookie 入库

```
POST /sessions/s1/navigate {"url":"https://site.com"}
  ├─ session.create_tab(url)
  │   ├─ tab.add_init_js(CF_WIDGET_FIX_JS)      # Turnstile 组件修复
  │   ├─ _apply_ua_metadata(tab)                 # 网络层 UA 头一致性
  │   └─ tab.get(url)
  ├─ ChallengeOrchestrator.resolve(tab)          # 全页挑战 + 嵌入组件
  ├─ cookies → session.cookie_store（按域名）
  └─ 返回 html/cookies/challenge
```

### 指纹注入（nexus-media）

```
用户浏览器（前端 JS 采集）→ nexus-media 后端
  → POST /api/browser/fingerprint → 按 user_id 映射 user_<id>
  → nexus-chrome POST /api/profiles（写入画像）
  → 会话带 fp_profile_id → BrowserPool 对应实例 → 呈现注入指纹
```

## API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/sessions` | 创建会话（`fp_profile_id` 绑定指纹画像）|
| `GET` | `/sessions` | 列出会话（含 fp_profile_id）|
| `DELETE` | `/sessions/{id}` | 销毁会话 |
| `POST` | `/sessions/{id}/navigate` | 导航 + 自动过挑战 + Cookie 入库 |
| `GET` | `/sessions/{id}/html` | 当前页面 HTML |
| `POST` | `/sessions/{id}/click` | 点击（DrissionPage 选择器）|
| `POST` | `/sessions/{id}/execute` | 执行 JS |
| `POST` | `/sessions/{id}/fetch` | 纯 HTTP（注入会话 Cookie）|
| `GET` | `/sessions/{id}/cookies` | 已存 Cookie |
| `GET` | `/api/profiles` | 画像列表（管理）|
| `POST` | `/api/profiles` | 创建/更新画像 |
| `GET` | `/api/profiles/{id}` | 拉取画像（带 HMAC 签名）|
| `POST` | `/api/profiles/{id}/rollback` | 回滚版本 |
| `POST` | `/api/profiles/{id}/gray` | 灰度发布 |
| `GET` | `/api/nodes/{id}/heartbeat` | 节点心跳 |
| `GET` | `/instances` | 运行中的指纹实例列表 |

## 目录结构

```
src/
├── main.py                    # FastAPI 入口（BrowserPool 生命周期）
├── config/settings.py         # 配置（MAX_BROWSERS/WINDOW_SIZE/指纹默认值…）
├── core/
│   ├── browser_manager.py     # BrowserPool + ChromeInstance（多实例）
│   ├── session.py             # Session + SessionManager（按 fp_profile_id 路由）
│   ├── cookie_store.py        # Cookie 隔离存储
│   └── fingerprint.py         # 预置 profile（default/stealth/paranoid，已去 JS 注入）
├── fp/
│   ├── profile.py             # 画像数据模型（FingerprintFields）
│   ├── render.py              # 画像 → FP_* env
│   ├── store.py               # SQLite 存储（版本/回滚/灰度/节点）
│   ├── service.py             # 画像解析 + 浏览器应用
│   ├── sync_client.py         # 远程拉取 + HMAC 验签
│   └── signing.py             # HMAC 签名
├── challenge/
│   ├── resolver.py            # ChallengeOrchestrator
│   ├── cloudflare.py          # 标准 + Turnstile 嵌入
│   ├── five_second_shield.py  # 五秒盾
│   ├── leichi.py              # 雷池
│   └── generic.py             # 通用
├── http/client.py             # httpx 封装（会话 Cookie 注入）
└── api/
    ├── routes.py              # 会话路由
    ├── fp_profiles.py         # 指纹配置中心路由
    └── schemas.py
```

## 技术选型

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 异步 + OpenAPI |
| 浏览器控制 | DrissionPage | CDP 协议，支持 shadow DOM |
| 浏览器二进制 | patched Chromium | fp_config 编译进 Blink，`CHROME_VERSION` 对齐 Chromium 版本 |
| 指纹渲染 | C++ fp_config | `FP_*` env → 进程级指纹（非 JS 注入）|
| 画像存储 | SQLite | 版本/回滚/灰度 |
| HTTP | httpx | 连接池、TLS |
| 日志 | loguru | 结构化 |

## 配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `CHROME_PATH` | `/opt/patched-chrome/chrome` | patched Chromium 路径 |
| `CHROME_VERSION` | `153.0.7991.0` | 发布版本（对齐 Chromium，GitHub Release）|
| `MAX_BROWSERS` | `5` | 并发指纹实例上限 |
| `WINDOW_SIZE` | `1366x768` | 窗口/显示/屏幕指纹尺寸 |
| `USER_DATA_PATH` | `~/.cache/nexus-chrome/user_data` | 默认实例数据 |
| `PROFILE_DATA_DIR` | `~/.cache/nexus-chrome/profiles` | 画像实例数据 |
| `FP_CENTER_URL` | `""` | 远程指纹配置中心（可选）|
| `FP_CENTER_SECRET` | `""` | 画像签名密钥 |
| `FP_ADMIN_TOKEN` / `FP_NODE_TOKEN` | `""` | 配置中心鉴权 |

## 发布与部署

- patched Chromium 构建：`fp_patches/build.sh`（版本自动取 Chromium VERSION）
- 发布：`gh release create chrome-<版本>` 到 `linyuan0213/nexus-chrome-bin`
- Docker：`ARG CHROME_VERSION` 下载 Release 包 + SHA256 校验，自包含补丁版 Chrome
- 私有保护：`fp_patches/`、`patched_libs/` 不进公共仓库（.gitignore）
