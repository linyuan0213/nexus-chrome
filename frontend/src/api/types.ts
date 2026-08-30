/** 与后端 src/api/schemas.py 对齐的请求/响应类型。 */

export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

// ---------- 会话 ----------

export interface SessionInfo {
  id: string;
  fingerprint: string;
  fp_profile_id: string | null;
  tabs: string[];
  active_tab: string | null;
  cookie_domains: string[];
}

export interface SessionListData {
  sessions: SessionInfo[];
  recovered: Array<Record<string, unknown>>;
}

export interface CreateSessionRequest {
  session_id: string;
  fingerprint_profile?: string;
  user_agent?: string | null;
  proxy?: string | null;
  fp_profile_id?: string | null;
}

export interface NavigateRequest {
  url: string;
  tab_name?: string | null;
  cookie?: string | null;
  referer?: string | null;
  timeout?: number;
}

export interface NavigateResult {
  url?: string;
  html?: string;
  challenge?: { detected?: boolean; solved?: boolean; type?: string };
  cookies?: CookieItem[];
  [key: string]: unknown;
}

export interface CookieItem {
  name: string;
  value: string;
  domain?: string;
  path?: string;
  expires?: number | string;
  [key: string]: unknown;
}

export interface TabInfo {
  name: string;
  url?: string;
  [key: string]: unknown;
}

export interface TabListData {
  active: string | null;
  tabs: TabInfo[];
}

export interface ClickRequest {
  selector: string;
  humanize?: boolean;
}

export interface DragRequest {
  selector: string;
  offset_x: number;
  offset_y?: number;
  duration?: number;
}

export interface InputRequest {
  selector: string;
  text: string;
}

export interface ExecuteRequest {
  script: string;
}

export interface FetchRequest {
  url: string;
  method?: string;
  headers?: Record<string, string> | null;
  data?: unknown;
  timeout?: number;
}

export interface RequestOperation {
  url: string;
  method?: string;
  headers?: Record<string, string> | null;
  data?: unknown;
  cookie?: string | null;
  navigate_if_challenge?: boolean;
  browser_fetch_on_challenge?: boolean;
  return_html?: boolean;
  timeout?: number;
}

export interface FetchResult {
  status?: number;
  headers?: Record<string, string>;
  body?: string;
  challenge_detected?: boolean;
  [key: string]: unknown;
}

export interface ScreenshotResult {
  tab?: string;
  full_page?: boolean;
  png_base64?: string;
  size?: number;
  [key: string]: unknown;
}

export interface DownloadRequestPayload {
  url: string;
  save_path?: string | null;
  timeout?: number;
}

export interface M3u8RequestPayload {
  url: string;
  timeout?: number;
}

export interface DownloadResult {
  path?: string;
  size?: number;
  base64?: string;
  filename?: string;
  [key: string]: unknown;
}

export interface M3u8Result {
  type?: string;
  playlists?: unknown[];
  segments?: unknown[];
  [key: string]: unknown;
}

export interface SetProxyRequest {
  proxy: string;
}

// ---------- 实例 / 状态 ----------

export interface InstanceInfo {
  key: string;
  port: number;
  alive: boolean;
  /** time.monotonic() 秒数，非 epoch，不能直接转日期 */
  last_used: number;
  ref_count: number;
  idle_seconds: number | null;
  /** X display 字符串，如 ":1" */
  display: string | null;
  vnc_port: number | null;
  web_port: number | null;
}

export interface StatusData {
  status: string;
  version: string;
  browser: string;
  instances: InstanceInfo[];
  timestamp: string;
}

// ---------- 指纹画像 ----------

export interface RolloutRule {
  percent: number;
  nodes: string[];
}

export interface FingerprintFields {
  ua: string;
  ua_full_version: string;
  ua_brand_version: string;
  languages: string[];
  platform: string;
  cores: number;
  memory: number;
  webgl_vendor: string;
  webgl_renderer: string;
  canvas_noise: boolean;
  canvas_seed: number;
  font_block: string[];
  rtc_ip: string;
  audio_noise: boolean;
  audio_rate: number;
  audio_seed: number;
  vendor: string;
  app_version: string;
  dnt: boolean;
  online: string;
  net_rtt: number;
  net_downlink: number;
  net_downlink_max: number;
  net_effective_type: string;
  screen_width: number;
  screen_height: number;
  screen_color_depth: number;
  gl_max_texture_size: number;
  pdf_enabled: number;
  webrtc_replace_host_ip: boolean;
  touch_points: number;
  uad_platform: string;
  uad_platform_version: string;
  uad_arch: string;
  uad_model: string;
  webgl_params: Record<string, number>;
  webgl_viewport_dims: number[];
  webgl_extensions_remove: string[];
  timezone: string;
  battery_level: number | null;
  battery_charging: boolean | null;
}

export interface FpProfile {
  profile_id: string;
  name: string;
  version: number;
  enabled: boolean;
  rollout: RolloutRule;
  fingerprint: FingerprintFields;
}

export interface ProfileSummary {
  profile_id: string;
  name?: string;
  version: number;
  enabled?: boolean;
  rollout?: RolloutRule;
  updated_at?: string;
  fingerprint?: Partial<FingerprintFields>;
  [key: string]: unknown;
}

export interface VersionRow {
  version: number;
  created_at?: string;
  operator?: string;
  [key: string]: unknown;
}

/** 节点拉取接口 GET /api/profiles/{id} 的响应（data 即指纹字段）。 */
export interface NodeProfileData {
  profile_id: string;
  version: number;
  data: FingerprintFields;
  signature?: string;
  issued_at?: string;
}

export interface VersionsData {
  profile_id: string;
  current_version: number;
  versions: VersionRow[];
}

// ---------- WebSocket 事件 ----------

export interface WsEvent {
  type: string;
  data?: Record<string, unknown>;
  ts?: number;
  [key: string]: unknown;
}
