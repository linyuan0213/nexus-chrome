# Nexus Chrome Manager — 前端设计文档

> 版本：v0.1（设计稿，未实现）
> 参考：[CloakBrowser-Manager](https://github.com/CloakHQ/CloakBrowser-Manager)（FastAPI + Web UI 的浏览器画像管理器）
> 后端：本仓库 FastAPI 服务（`/sessions`、`/api/profiles`、`/instances`、`/ws/events`）

## 1. 目标与定位

为 nexus-chrome 提供 Web 管理界面（**Nexus Chrome Manager**），将现有的 curl/REST 操作全部可视化：

- **会话管理**：创建/销毁会话、绑定指纹画像、自动过盾导航、截图、Cookie 查看、页面交互（点击/输入/拖拽/执行 JS）
- **指纹画像管理**：画像 CRUD、版本历史、回滚、灰度发布（替代手写 `POST /api/profiles`）
- **实例监控**：浏览器实例池状态、VNC 在线查看、手动回收
- **实时事件**：`/ws/events` 事件流可视化
- **请求调试台**：`/fetch`、`/request`、`/m3u8`、`/download` 的图形化调试入口

非目标（本期不做）：
- 多用户/权限体系（单 token 鉴权，与 `FP_ADMIN_TOKEN` 对齐）
- 指纹采集注入（属于 nexus-media 侧职责）
- 修改后端 API（前端只消费现有接口，发现缺口时先提后端变更）

## 2. 假设（待确认）

1. 前端独立目录 `frontend/`，与后端同仓库（monorepo），构建产物由 nginx 在同一 9850 端口提供
2. 部署形态以 Docker 容器为主（无 GPU Linux 服务器），浏览器查看走 noVNC iframe
3. 鉴权方式：可选单 Bearer Token（对齐后端 `FP_ADMIN_TOKEN`），默认无鉴权本地使用
4. 主要使用场景为桌面端，移动端做基本适配（可查看/简单操作）
5. 技术栈锁定 Vue 3 + Vite + TypeScript

→ 如有出入请在实施前指出。

## 3. 技术栈

| 类别 | 选型 | 理由 |
|------|------|------|
| 框架 | Vue 3.5（`<script setup>` + Composition API） | 主流、生态成熟 |
| 构建 | Vite 7 | 快、原生 ESM、dev proxy 完善 |
| 语言 | TypeScript 5（strict） | 与 API schema 对齐，减少联调错误 |
| 组件库 | Naive UI | TS 优先、Table/Form/Modal 完善、主题可定制 |
| 样式 | Tailwind CSS v4 + CSS 变量主题 | 快速布局；颜色全部走 `hsl(var(--*))` 变量 |
| 状态 | Pinia | 官方标准 |
| 路由 | Vue Router 4 | 官方标准 |
| HTTP | ofetch（`$fetch` 封装） | 轻量、自动 JSON、拦截器友好 |
| WebSocket | 原生 WS + `@vueuse/core` `useWebSocket` | 自动重连 |
| 图标 | `@iconify/vue`（统一 `lucide:` 前缀） | 禁止内联 SVG |
| 工具库 | `@vueuse/core`、`dayjs` | — |
| 测试 | Vitest + @vue/test-utils + Playwright（e2e） | 与 Vite 集成 |
| 规范 | ESLint + Prettier + Stylelint | — |

**明确不引入**：Vuex、Element Plus（与 Naive UI 二选一）、jQuery、内联 SVG 图标库。

## 4. 项目结构

```
nexus-chrome/
├── frontend/                        # 前端子项目（pnpm 管理，独立 lockfile）
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts               # dev proxy：/api|/sessions|/instances|/ws → 127.0.0.1:9850
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── public/
│   ├── src/
│   │   ├── main.ts                  # 装配 Pinia/Router/Naive UI
│   │   ├── App.vue
│   │   ├── styles/
│   │   │   ├── index.css            # tailwind 入口
│   │   │   └── theme.css            # hsl(var(--*)) 主题变量（亮/暗）
│   │   ├── router/
│   │   │   └── index.ts             # 路由表 + 鉴权守卫
│   │   ├── api/                     # API 层：每资源一个模块，全部 TS 类型化
│   │   │   ├── client.ts            # ofetch 实例（baseURL、token 注入、错误归一化）
│   │   │   ├── types.ts             # 与后端 schemas.py / ApiResponse 对齐的类型
│   │   │   ├── sessions.ts          # /sessions*（导航/点击/截图/标签页…）
│   │   │   ├── profiles.ts          # /api/profiles*（CRUD/版本/回滚/灰度）
│   │   │   ├── instances.ts         # /instances、/status
│   │   │   └── events.ts            # /ws/events 封装（useEventStream）
│   │   ├── stores/                  # Pinia（按资源划分）
│   │   │   ├── sessions.ts
│   │   │   ├── profiles.ts
│   │   │   ├── instances.ts
│   │   │   ├── events.ts            # 事件环形缓冲（最近 N 条）+ 未读计数
│   │   │   └── app.ts               # 主题、token、服务状态轮询
│   │   ├── composables/
│   │   │   ├── usePolling.ts        # 可暂停轮询（页面不可见时暂停）
│   │   │   ├── useEventStream.ts    # WS 封装：订阅类型过滤、断线重连
│   │   │   └── useVncUrl.ts         # display → /chromeN/ URL
│   │   ├── layouts/
│   │   │   └── DefaultLayout.vue    # 侧边导航 + 顶栏（服务状态徽章、主题切换、Token 设置）
│   │   ├── views/                   # 页面（与路由一一对应）
│   │   │   ├── DashboardView.vue
│   │   │   ├── sessions/
│   │   │   │   ├── SessionListView.vue
│   │   │   │   └── SessionDetailView.vue
│   │   │   ├── profiles/
│   │   │   │   ├── ProfileListView.vue
│   │   │   │   └── ProfileDetailView.vue
│   │   │   ├── InstancesView.vue
│   │   │   ├── EventsView.vue
│   │   │   ├── PlaygroundView.vue   # 请求调试台
│   │   │   └── SettingsView.vue
│   │   └── components/              # 业务组件（按域分目录）
│   │       ├── sessions/            # SessionCard / CreateSessionDialog / NavigateBar /
│   │       │                        # TabManager / ScreenshotPanel / CookieTable /
│   │       │                        # InteractPanel（click/input/drag/execute）/ ProxyDialog
│   │       ├── profiles/            # ProfileForm / FingerprintFieldsEditor /
│   │       │                        # VersionTimeline / GrayPublishDialog
│   │       ├── instances/           # InstanceCard / VncFrame
│   │       └── common/              # StatusBadge / JsonViewer / CodeEditor(execute JS) / EmptyState
│   ├── tests/
│   │   ├── unit/                    # Vitest（stores/api/composables）
│   │   └── e2e/                     # Playwright（关键流程）
│   └── .env.development             # VITE_API_TARGET=http://127.0.0.1:9850
├── deploy/nginx.conf                # 增加 /ui/ location（见 §9）
└── docs/frontend-design.md          # 本文档
```

## 5. 路由与页面设计

| 路径 | 页面 | 说明 |
|------|------|------|
| `/ui/` | Dashboard | 服务状态卡片（`/status`）、运行实例数/会话数统计、最近事件流、快捷入口 |
| `/ui/sessions` | 会话列表 | 卡片/表格视图、搜索、创建会话对话框、删除确认、可恢复会话提示（`recovered`） |
| `/ui/sessions/:id` | 会话详情 | 核心工作区，见 §5.1 |
| `/ui/profiles` | 画像列表 | 表格：profile_id / 名称 / 版本 / 灰度状态 / 更新时间；新建画像 |
| `/ui/profiles/:id` | 画像详情 | 指纹字段编辑器 + 版本时间线 + 回滚 + 灰度发布 |
| `/ui/instances` | 实例监控 | 实例卡片：key、display、web_port、运行时长、VNC 直达、关闭按钮 |
| `/ui/events` | 事件中心 | WS 事件流（session_created/deleted 等），类型过滤、暂停、清空 |
| `/ui/playground` | 请求调试台 | 选会话 → fetch/request/m3u8/download 表单 → 响应查看器 |
| `/ui/settings` | 设置 | API Token、主题（亮/暗/跟随系统）、轮询间隔、服务配置只读展示 |

### 5.1 会话详情页（核心页面）

顶部为会话信息条（session_id、绑定画像、代理、创建时间）+ 操作（删除、切代理、打开 VNC）。主体为左右分栏：

```
┌─────────────────────────────┬──────────────────────────┐
│ 左栏：浏览器视图              │ 右栏（Tabs）：            │
│ ┌─────────────────────────┐ │  ▸ 标签页：TabManager     │
│ │ NavigateBar：URL 输入     │ │  ▸ Cookie：按域名分组表格  │
│ │ [导航并过盾] [截图] [VNC] │ │  ▸ 交互：click/input/drag │
│ ├─────────────────────────┤ │           /execute JS     │
│ │ 截图预览 / noVNC iframe   │ │  ▸ HTML：源码查看         │
│ │ （可切换：截图模式 /       │ │  ▸ 网络：fetch/request   │
│ │   VNC 实时模式）          │ │           调试表单        │
│ └─────────────────────────┘ │                          │
└─────────────────────────────┴──────────────────────────┘
```

- **NavigateBar**：URL 输入 + 超时设置，调用 `POST /sessions/{id}/navigate`，loading 期间显示"过盾中…"，返回后展示 `challenge` 结果与耗时
- **截图/VNC 切换**：截图模式调用 `/screenshot`（支持整页）；VNC 模式 iframe 嵌入 `/chrome{display}/?autoconnect=true`（display 从会话所属实例取）
- **标签页 Tab**：列出/新建/切换/关闭（`/tabs` 系列接口），切换后自动刷新截图
- **交互 Tab**：四个表单卡片（点击含 humanize 开关、拖拽含偏移/时长、输入、JS 编辑器含运行结果 JSON 展示）

### 5.2 画像详情页

- **FingerprintFieldsEditor**：分组表单（基础：UA/platform/uad_platform；硬件：cores/memory；WebGL：vendor/renderer/params；区域：timezone/locale；噪声开关说明提示），字段名与后端 `FingerprintFields` 一一对应，留空字段提示"服务端按平台自动生成自洽值"
- **VersionTimeline**：`GET /api/profiles/{id}/versions`，每版本显示 diff 摘要 + 回滚按钮
- **GrayPublishDialog**：百分比滑块或节点 ID 列表（`POST /api/profiles/{id}/gray`）

## 6. API 对接层

`api/client.ts` 统一处理：

```ts
// 统一响应处理：后端 ApiResponse { code, message, data }，code !== 0 抛业务错误
export const api = ofetch.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '/',
  onRequest({ options }) {
    const token = useAppStore().token;
    if (token) options.headers.set('Authorization', `Bearer ${token}`);
  },
  onResponseError({ response }) {
    throw new ApiError(response.status, response._data?.detail ?? '请求失败');
  },
});
```

**类型对齐**：`api/types.ts` 手工维护与 `src/api/schemas.py` 对应的 TS 接口（`CreateSessionRequest`、`NavigateRequest`、`RequestOperation` 等），并在 CI 中加契约检查（见 §10 开放问题：未来可由 OpenAPI 生成）。

**接口对接表**（前端模块 → 后端端点）：

| 前端模块 | 后端端点 | 页面 |
|----------|----------|------|
| `instances.getStatus` | `GET /status` | Dashboard / 顶栏徽章 |
| `instances.list/remove` | `GET/DELETE /instances[/{key}]` | Instances |
| `sessions.create/list/remove` | `POST/GET/DELETE /sessions` | SessionList |
| `sessions.navigate` | `POST /sessions/{id}/navigate` | 详情 NavigateBar |
| `sessions.screenshot/html/cookies` | `POST /screenshot`、`GET /html`、`GET /cookies` | 详情各 Tab |
| `sessions.click/drag/input/execute` | `POST /click|drag|input|execute` | 交互 Tab |
| `sessions.tabs.*` | `GET/POST/DELETE /tabs*`、`POST /tabs/switch` | 标签页 Tab |
| `sessions.fetch/request/download/m3u8` | `POST /fetch|request|download|m3u8` | 网络 Tab / Playground |
| `sessions.setProxy` | `POST /sessions/{id}/proxy` | ProxyDialog |
| `profiles.*` | `GET/POST /api/profiles`、`GET /{id}/versions`、`POST /{id}/rollback|gray` | Profiles |
| `events.subscribe` | `WS /ws/events?types=...` | Events / 全局通知 |

**错误处理约定**：404 → "会话不存在（可能已被回收）"并跳转列表；500 → 显示 `detail`；网络错误 → 全局 message + 状态徽章变红。

## 7. 实时通信设计

- 全局单例 `useEventStream`：`useWebSocket(`${base}/ws/events`)`，指数退避重连（1s→30s 上限），页面不可见时保持连接但暂停渲染更新
- `stores/events.ts` 维护环形缓冲（默认 500 条），按 `type` 过滤订阅
- `session_created` / `session_deleted` 事件自动触发 `sessions` store 局部刷新（替代全量轮询）；实例状态保留 10s 轮询兜底
- 顶栏提供连接状态指示灯（绿/黄/红）

## 8. UI 规范

- **颜色**：禁止硬编码颜色与 Tailwind 颜色类；统一 `hsl(var(--card))`、`hsl(var(--primary))`、`hsl(var(--border))`、`hsl(var(--muted-foreground))`、`hsl(var(--success))`、`hsl(var(--warning))`、`hsl(var(--destructive))` 等 CSS 变量；暗色主题切换只切换 `:root` 变量值
- **图标**：统一 `<Icon icon="lucide:xxx" />`（`@iconify/vue`），禁止内联 SVG
- **状态语义**：实例运行中=success、回收中=warning、异常=destructive；挑战通过=success、失败=destructive、过盾中=info 旋转
- **布局**：侧边栏 240px（折叠 64px），内容区 `max-w-screen-2xl`；会话详情左右分栏在 <1024px 时改为上下堆叠
- **移动端**：列表页卡片化；详情页分栏改 Tabs；操作按钮不隐藏、保证可触摸
- **JSON/HTML 展示**：统一 `JsonViewer`（折叠/复制）；JS 编辑器用轻量 `CodeEditor`（textarea + 高亮，不引入 Monaco，除非后续需要）

## 9. 构建与部署集成

**开发**：

```bash
cd frontend && pnpm install && pnpm dev   # vite dev server :5173，proxy → 127.0.0.1:9850
```

`vite.config.ts` proxy 目标：

```ts
proxy: {
  '/sessions': target, '/instances': target, '/status': target,
  '/api': target,
  '/ws': { target, ws: true },
  '/chrome1/': { target, ws: true }, /* …或按环境变量动态生成 */
}
```

**生产**：`pnpm build` 产物 `frontend/dist/`，由同一 nginx（9850）提供，在 `deploy/nginx.conf` 中**先于** `location /` 插入：

```nginx
location /ui/ {
  alias /app/frontend/dist/;
  try_files $uri $uri/ /ui/index.html;   # SPA history 路由回退
}
```

Dockerfile 增加前端构建阶段（`node:22` 构建 → 拷贝 dist 到运行时镜像），保持单容器交付。noVNC iframe 路径 `/chromeN/` 与前端 `/ui/` 同域，无跨域问题。

## 10. 测试策略

| 层级 | 工具 | 范围 |
|------|------|------|
| 单元 | Vitest + @vue/test-utils | stores（会话增删、事件缓冲）、composables（usePolling 暂停/恢复）、api client（错误归一化） |
| 组件 | Vitest + @vue/test-utils | FingerprintFieldsEditor 字段映射、NavigateBar 状态流转 |
| e2e | Playwright | 关键路径：创建会话 → 导航 → 截图可见 → 删除；画像创建 → 版本+1 → 回滚 |
| 契约 | CI 脚本 | 校验 `api/types.ts` 与后端 OpenAPI（`/openapi.json`）字段漂移（warning 级） |

命令：`pnpm test`（unit）、`pnpm test:e2e`、`pnpm lint`、`pnpm typecheck`（`vue-tsc --noEmit`）。

## 11. 边界

- **Always**：提交前跑 `pnpm lint && pnpm typecheck && pnpm test`；颜色/图标遵守 §8；API 类型变更同步更新 `api/types.ts`
- **Ask first**：新增依赖；修改 `deploy/nginx.conf` / Dockerfile；引入重型编辑器（Monaco）
- **Never**：提交 token 等密钥；在前端持久化敏感信息到 localStorage 以外位置；绕过统一 `api/client.ts` 直接发请求

## 12. 里程碑

| 阶段 | 内容 | 验收 |
|------|------|------|
| M1 脚手架 | Vite 项目、主题、布局、路由、api client、token 设置 | dev server 可访问空壳五个页面 |
| M2 会话闭环 | 会话列表/创建/删除 + 详情（导航、截图、标签页） | e2e：创建→导航→截图→删除通过 |
| M3 画像管理 | 画像 CRUD、版本、回滚、灰度 | 创建画像→版本+1→回滚通过 |
| M4 实例与事件 | Instances 页、VNC iframe、WS 事件中心、Dashboard | 事件实时到达；VNC 可交互 |
| M5 调试台与打磨 | Playground、移动端适配、部署集成、契约检查 | Docker 镜像内 `/ui/` 可用 |

## 13. 开放问题（已解决/实施记录）

1. **API 类型生成**：后端 FastAPI 自带 OpenAPI，是否引入 `openapi-typescript` 生成类型替代手写 `types.ts`？（建议 M2 后评估）
2. ~~**鉴权**~~ ✅ 已实现：人机分离双通道
   - 用户登录：登录页输入 `AUTH_PASSWORD` → `POST /api/auth/login` 签发 24h 短期 session token；401 自动跳登录页；顶栏登出
   - 第三方程序：API Key（`ncmk_` 前缀，SHA-256 存储，scope 路径级限权，可吊销）；管理页 `/ui/api-keys`
   - 后端：全局认证中间件（`src/main.py` auth_middleware，白名单：/ui、/chromeN、/status、登录接口）+ WS `/ws/events` query 参数鉴权 + FP 接口兼容 `FP_ADMIN_TOKEN`/`FP_NODE_TOKEN`
   - 未设置 `AUTH_PASSWORD` 时认证完全关闭（本地模式），API Keys 页有明确提示
3. ~~**VNC 密码**~~ ✅ 已实现：后端 `/api/auth/me` 认证后下发（`/status` 已移除敏感字段）；前端仍可在设置页本地覆盖
4. **截图 vs VNC 默认模式**：无 GPU 容器内 VNC 流畅度待实测，默认先用截图模式更稳妥。

## 14. 实施后的后端修复记录

- **Xvfb 残留 socket 误判**（`src/core/browser_manager/process.py`）：容器重启后 `/tmp/.X11-unix/Xn` 残留导致 Chrome 无法启动 → 改用 unix socket 连接探测判断存活性
- **CF 盒子挑战误分流**（`src/challenge/cloudflare.py`）：有可定位的 Turnstile 组件时优先点击（原"托管优先"逻辑会导致 audiences.me 等站点永不点击复选框）
- **人性化点击**（`src/utils/challenge_utils.py` + `humanize.py`）：Turnstile 复选框改贝塞尔轨迹点击（坐标 = iframe 绝对偏移 + 元素中心 + 抖动），最多重试 3 次
- **过盾性能**：`page.html` 全量读取 6 次 → 1 次（标题快路径）+ `css:iframe` 定位（`tag:iframe` 在跨域场景约 10s）+ 一次挑战只连接一次跨域帧
- **VNC 进程泄漏**（`src/core/browser_manager/vnc.py`）：`VncStack` 按端口注册表 + 部分死亡时先整体停止再拉起，修复 websockify 重复占用端口（曾导致 noVNC 能看不能点）
- **遗留会话膨胀**（`src/core/session/manager.py`）：注册表记录带 `updated_at`，超 7 天自动裁剪；`DELETE /sessions/recovered` 手动清除
- **截图免导航**（`src/core/session/base.py`）：`_get_active_tab` 无活跃标签页时自动创建 about:blank
- **Cookie 删除**：`DELETE /sessions/{id}/cookies?domain=&name=`（镜像存储级）
