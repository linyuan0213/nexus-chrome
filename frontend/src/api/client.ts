/** 统一 HTTP 客户端：ApiResponse 解包、错误归一化、Bearer Token 注入、401 跳转登录。 */

import { ofetch } from 'ofetch';

import type { ApiResponse } from './types';

const TOKEN_KEY = 'ncm_token';

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? '';
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** 401 → 清除凭证并跳转登录页（登录页/登录接口自身除外，避免循环）。 */
function handleUnauthorized(url?: string): void {
  if (url?.includes('/api/auth/login')) return;
  setToken('');
  const loginPath = `${import.meta.env.BASE_URL}login`;
  if (!location.pathname.endsWith('/login')) {
    location.assign(loginPath);
  }
}

const raw = ofetch.create({
  baseURL: '/',
  retry: 0,
  onRequest({ options }) {
    const token = getToken();
    if (token) {
      const headers = new Headers(options.headers);
      headers.set('Authorization', `Bearer ${token}`);
      options.headers = headers;
    }
  },
  onResponseError({ request, response }) {
    if (response.status === 401) handleUnauthorized(String(request));
    const detail = response._data?.detail ?? response._data?.message;
    throw new ApiError(response.status, String(detail ?? `请求失败 (${response.status})`));
  },
});

/** 解包后端 ApiResponse；code !== 0 视为业务错误。 */
export async function unwrap<T>(p: Promise<ApiResponse<T>>): Promise<T> {
  const res = await p;
  if (res && typeof res === 'object' && 'code' in res && res.code !== 0) {
    throw new ApiError(res.code, res.message || '业务错误');
  }
  return res.data;
}

export function get<T>(url: string, query?: Record<string, unknown>): Promise<T> {
  return unwrap(raw<ApiResponse<T>>(url, { method: 'GET', query }));
}

export function post<T>(url: string, body?: unknown, query?: Record<string, unknown>): Promise<T> {
  return unwrap(raw<ApiResponse<T>>(url, { method: 'POST', body: body as BodyInit, query }));
}

export function del<T>(url: string, query?: Record<string, unknown>): Promise<T> {
  return unwrap(raw<ApiResponse<T>>(url, { method: 'DELETE', query }));
}

/** 原始 GET：/status、/instances 等端点直接返回对象（非 ApiResponse 包装）。 */
export function getRaw<T>(url: string, query?: Record<string, unknown>): Promise<T> {
  return raw<T>(url, { method: 'GET', query });
}

/** WebSocket 事件流地址（同源，认证开启时附带 token）。 */
export function wsEventsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const base = `${proto}//${location.host}/ws/events`;
  const token = getToken();
  return token ? `${base}?Authorization=${encodeURIComponent(`Bearer ${token}`)}` : base;
}
