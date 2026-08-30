/** /sessions 会话相关 API。 */

import { get, post, del } from './client';
import type {
  ClickRequest,
  CreateSessionRequest,
  DownloadRequestPayload,
  DragRequest,
  ExecuteRequest,
  FetchRequest,
  FetchResult,
  InputRequest,
  M3u8RequestPayload,
  NavigateRequest,
  NavigateResult,
  RequestOperation,
  SessionInfo,
  SessionListData,
  SetProxyRequest,
  ScreenshotResult,
  TabListData,
} from './types';

export function createSession(body: CreateSessionRequest): Promise<SessionInfo> {
  return post('/sessions', body);
}

export function listSessions(): Promise<SessionListData> {
  return get('/sessions');
}

export function deleteSession(id: string): Promise<null> {
  return del(`/sessions/${encodeURIComponent(id)}`);
}

export function clearRecoveredSessions(): Promise<null> {
  return del('/sessions/recovered');
}

export function navigate(id: string, body: NavigateRequest): Promise<NavigateResult> {
  return post(`/sessions/${encodeURIComponent(id)}/navigate`, body);
}

export function getHtml(id: string): Promise<string> {
  return get(`/sessions/${encodeURIComponent(id)}/html`);
}

export function getCookies(id: string, domain?: string): Promise<Record<string, Record<string, string>>> {
  return get(`/sessions/${encodeURIComponent(id)}/cookies`, domain ? { domain } : undefined);
}

export function deleteCookie(id: string, domain: string, name: string): Promise<null> {
  return del(`/sessions/${encodeURIComponent(id)}/cookies`, { domain, name });
}

export function click(id: string, body: ClickRequest): Promise<null> {
  return post(`/sessions/${encodeURIComponent(id)}/click`, body);
}

export function drag(id: string, body: DragRequest): Promise<null> {
  return post(`/sessions/${encodeURIComponent(id)}/drag`, body);
}

export function inputText(id: string, body: InputRequest): Promise<null> {
  return post(`/sessions/${encodeURIComponent(id)}/input`, body);
}

export function executeJs(id: string, body: ExecuteRequest): Promise<{ result: unknown }> {
  return post(`/sessions/${encodeURIComponent(id)}/execute`, body);
}

export function httpFetch(id: string, body: FetchRequest): Promise<FetchResult> {
  return post(`/sessions/${encodeURIComponent(id)}/fetch`, body);
}

export function unifiedRequest(id: string, body: RequestOperation): Promise<unknown> {
  return post(`/sessions/${encodeURIComponent(id)}/request`, body);
}

export function listTabs(id: string): Promise<TabListData> {
  return get(`/sessions/${encodeURIComponent(id)}/tabs`);
}

export function createTab(id: string, name?: string, url?: string): Promise<unknown> {
  return post(`/sessions/${encodeURIComponent(id)}/tabs`, { name: name || null, url: url || null });
}

export function switchTab(id: string, name: string): Promise<unknown> {
  return post(`/sessions/${encodeURIComponent(id)}/tabs/switch`, { name });
}

export function closeTab(id: string, tabName: string): Promise<null> {
  return del(`/sessions/${encodeURIComponent(id)}/tabs/${encodeURIComponent(tabName)}`);
}

export function screenshot(id: string, tabName?: string, fullPage = false): Promise<ScreenshotResult> {
  return post(`/sessions/${encodeURIComponent(id)}/screenshot`, {
    tab_name: tabName || null,
    full_page: fullPage,
  });
}

export function download(id: string, body: DownloadRequestPayload): Promise<unknown> {
  return post(`/sessions/${encodeURIComponent(id)}/download`, body);
}

export function detectM3u8(id: string, body: M3u8RequestPayload): Promise<unknown> {
  return post(`/sessions/${encodeURIComponent(id)}/m3u8`, body);
}

export function setProxy(id: string, body: SetProxyRequest): Promise<unknown> {
  return post(`/sessions/${encodeURIComponent(id)}/proxy`, body);
}

export type { DownloadRequestPayload, M3u8RequestPayload };
