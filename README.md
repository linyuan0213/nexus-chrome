# Nexus Chrome 服务器

## 项目结构

```
nexus-chrome/
├── src/                    # 源代码
│   ├── __init__.py
│   ├── main.py            # 主 FastAPI 应用
│   ├── config/            # 配置模块
│   │   ├── __init__.py
│   │   └── settings.py    # 应用设置和常量
│   ├── core/              # 核心功能
│   │   ├── __init__.py
│   │   ├── browser_manager.py  # 浏览器管理
│   │   ├── cookie_store.py     # Cookie 共享存储
│   │   ├── fingerprint.py      # 指纹管理器
│   │   └── session.py          # Session + SessionManager
│   ├── challenge/         # 挑战解析器
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── resolver.py
│   │   ├── cloudflare.py
│   │   ├── five_second_shield.py
│   │   ├── leichi.py
│   │   └── generic.py
│   ├── http/              # HTTP 客户端
│   │   ├── __init__.py
│   │   └── client.py
│   ├── api/               # API 层
│   │   ├── __init__.py
│   │   ├── schemas.py     # 请求/响应模式
│   │   └── routes.py      # API 路由处理器
│   └── utils/             # 工具函数
│       ├── __init__.py
│       └── challenge_utils.py
├── main.py                # 应用入口点
├── pyproject.toml         # 项目配置和依赖管理（uv）
├── Dockerfile            # Docker 配置
├── supervisord.conf      # 进程管理
├── start.sh              # 启动脚本
└── README.md             # 本文件
```

## 功能特性

- **Session 隔离浏览器自动化**：每个站点/流程独立 Cookie、标签页、指纹
- **自动过盾**：Cloudflare、五秒盾、雷池、通用 WAF
- **Cookie 共享**：浏览器过盾后自动复用 Cookie 到 HTTP 快路径
- **RESTful API**：基于 FastAPI 的异步接口
- **Docker 支持**：使用 Docker 轻松部署
- **网页 VNC**：通过 noVNC 查看浏览器会话（容器模式）

## API 端点

### 根路径
- `GET /` - API 信息
- `GET /status` - 服务状态

### Session 管理
- `POST /sessions` - 创建会话
- `GET /sessions` - 列出会话
- `DELETE /sessions/{id}` - 删除会话

### 浏览器操作（基于 Session）
- `POST /sessions/{id}/navigate` - 浏览器导航（自动过盾、提取 Cookie）
- `GET /sessions/{id}/html` - 获取当前页面 HTML
- `GET /sessions/{id}/cookies` - 获取已存储 Cookie
- `POST /sessions/{id}/click` - 在当前页面点击元素
- `POST /sessions/{id}/input` - 在当前页面输入文本
- `POST /sessions/{id}/execute` - 执行自定义 JavaScript

### HTTP 快路径
- `POST /sessions/{id}/fetch` - 使用 Session Cookie 发起纯 HTTP 请求

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
uv run uvicorn src.main:app --host 0.0.0.0 --port 9850
```

### Docker 部署

1. 构建镜像：
```bash
docker build -t nexus-chrome-novnc .
```

2. 运行容器：

```bash
docker run --shm-size=2g -p 9850:9850 -p 6080:6080 -d nexus-chrome-novnc
```

### 网页 VNC 访问

启动容器后，访问 `http://localhost:6080` 查看浏览器会话。

**端口说明：**
- `9850`: FastAPI 服务器端口
- `6080`: noVNC 网页界面端口
- `5900`: VNC 服务器端口（内部使用）

### 包安装

```bash
uv pip install -e .
```

## 使用示例

### 创建会话并导航（自动过盾）

```bash
# 创建会话
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

### 交互操作（签到等）

```bash
# 输入文本
curl -X POST http://localhost:9850/sessions/work/input \
  -H "Content-Type: application/json" \
  -d '{"selector": "#username", "text": "admin"}'

# 点击元素
curl -X POST http://localhost:9850/sessions/work/click \
  -H "Content-Type: application/json" \
  -d '{"selector": "#submit"}'
```

## 配置

环境变量：
- `APP_HOST`: 服务器主机（默认：0.0.0.0）
- `APP_PORT`: 服务器端口（默认：9850）
- `CHROME_PATH`: 自定义 Chrome 浏览器路径
- `HEADLESS_MODE`: 无头模式（默认：`--headless=new`）
- `REMOTE_CHROME_ADDRESS`: 远程 Chrome CDP 地址，如 `127.0.0.1:9222`
- `VNC_PASSWORD`: VNC 密码（默认：password，部署时必须修改）
- `CHALLENGE_TIMEOUT`: 挑战等待超时（默认：30 秒）
- `HTTP_CLIENT_TIMEOUT`: HTTP 客户端超时（默认：30 秒）
- `USER_DATA_PATH`: Chrome 用户数据目录路径（默认：`~/.cache/nexus-chrome/user_data`）
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

### 代码结构

项目遵循清晰架构模式：

- **src/config**: 应用配置和常量
- **src/core**: 核心业务逻辑、浏览器管理、Session、Cookie、指纹
- **src/challenge**: 挑战解析器（Cloudflare、五秒盾、雷池等）
- **src/http**: 基于 httpx 的 HTTP 客户端，与 Session Cookie 集成
- **src/api**: API 路由和请求/响应模式
- **src/utils**: 工具函数和辅助程序

## 许可证

MIT License - 详见 LICENSE 文件。
