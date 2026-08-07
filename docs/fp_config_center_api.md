# 指纹配置 API（内建于 nexus-chrome）

指纹画像管理、灰度/回滚、HMAC 签名下发、节点心跳。内建于 nexus-chrome 服务（`/api/profiles`），
供启动 patched Chromium 时注入 `FP_*` 环境变量。

- **Base URL**：`https://<nexus-chrome>/api`
- **数据格式**：JSON

---

## 数据模型：指纹画像 Profile

```json
{
  "profile_id": "site-audiences",
  "name": "Audiences 站点画像",
  "version": 12,
  "enabled": true,
  "rollout": { "percent": 100, "nodes": [] },
  "fingerprint": {
    "ua": "Mozilla/5.0 (X11; Linux x86_64) ... Chrome/151.0.0.0 Safari/537.36",
    "ua_full_version": "151.0.7922.71",
    "ua_brand_version": "151",
    "languages": ["zh-CN", "zh", "en-US", "en"],
    "platform": "Linux x86_64",
    "cores": 8,
    "memory": 8,
    "webgl_vendor": "Google Inc. (Intel)",
    "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.5 (Core Profile) Mesa 25.0.7",
    "canvas_noise": false,
    "gl_max_texture_size": 16384,
    "webrtc_replace_host_ip": true,
    "uad_platform": "Linux",
    "uad_arch": "x86_64",
    "uad_model": ""
  }
}
```

`fingerprint` 字段对应 patched Chromium 的 `FP_*` 环境变量（列表用逗号连接、布尔转 0/1）。
`canvas_seed=0` 表示每次启动随机。渲染逻辑见 `src/fp/render.py`。

> 注意：`canvas_noise` / `audio_noise` 默认关闭 —— 任何像素噪声都会被测为 "rgba noise"
> （真实浏览器 canvas 渲染是确定性的）。WebGL 渲染器必须使用 Linux Mesa 风格字符串
> （Windows 风格 "Build 31.0.101.x" 在 Linux 上自相矛盾，会被检测为 WebGL 异常）。

---

## 接口

### 1. 画像列表

`GET /api/profiles`

```json
{
  "code": 0, "message": "ok",
  "data": { "profiles": [ { "profile_id": "site-audiences", "name": "...", "version": 12, "enabled": true, "rollout": {...} } ] }
}
```

### 2. 拉取最新画像（带签名）

`GET /api/profiles/{profile_id}`

节点启动浏览器前调用。响应带 `signature`（HMAC-SHA256，密钥 `FP_CENTER_SECRET`）：

```json
{
  "code": 0, "message": "ok",
  "data": {
    "profile_id": "site-audiences",
    "version": 12,
    "data": { "ua": "...", "cores": 8, "...": "..." },
    "signature": "8f3a4b...c1",
    "issued_at": "2026-08-04T23:00:00Z"
  }
}
```

签名：`HMAC_SHA256(secret, canonical(data) + "|" + version)`。

### 3. 历史版本

`GET /api/profiles/{profile_id}/versions`

### 4. 创建 / 更新

`POST /api/profiles`

请求体为完整 Profile（`profile_id` 已存在则 version +1 并保留历史）：

```json
{ "profile_id": "site-audiences", "name": "...", "fingerprint": {...}, "rollout": {...} }
```

### 5. 回滚

`POST /api/profiles/{profile_id}/rollback?to_version=11`

### 6. 灰度

`POST /api/profiles/{profile_id}/gray`

```json
{ "percent": 20, "nodes": ["node-audiences-01"] }
```

### 7. 节点心跳

`GET /api/nodes/{node_id}/heartbeat?profile_id=x&profile_version=1&browser=chrome_151_fp12`

```json
{ "code": 0, "message": "ok", "data": { "status": "ok", "latest_version": 12, "should_reload": true } }
```

`should_reload=true` 表示中心有新版本，节点应在下一会话启动时重新拉取。

---

## 使用流程

```
1. POST /api/profiles                      # 创建画像
2. 会话/站点 → profile_id
   → src/fp/sync_client.get_profile()      # 读本地 store（或远程主节点）
   → src/fp/render.render_env()            # 渲染 FP_* 环境变量
   → browser_manager.ensure_browser_with_env(fp_env)  # 注入并启动浏览器
3. GET /api/nodes/{id}/heartbeat           # 上报生效版本 + 指纹快照
```

多节点场景：节点可用 `FP_CENTER_URL` 指向主节点 nexus-chrome 拉取画像（`src/fp/sync_client.py` 自动回退）。
