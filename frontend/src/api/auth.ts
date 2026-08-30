/** 认证 API。 */

import { get, post, del } from './client';

export interface AuthConfig {
  enabled: boolean;
}

export interface AuthMe {
  vnc_enabled: boolean;
  vnc_password: string | null;
}

export interface ApiKeyRecord {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  revoked: boolean;
}

export interface CreatedApiKey extends ApiKeyRecord {
  /** 明文 key，仅创建时返回一次 */
  key: string;
}

export function getAuthConfig(): Promise<AuthConfig> {
  return get('/api/auth/config');
}

export function login(password: string): Promise<{ token: string }> {
  return post('/api/auth/login', { password });
}

export function logout(): Promise<null> {
  return post('/api/auth/logout');
}

export function getAuthMe(): Promise<AuthMe> {
  return get('/api/auth/me');
}

export function listApiKeys(): Promise<{ keys: ApiKeyRecord[] }> {
  return get('/api/auth/keys');
}

export function createApiKey(name: string, scopes: string[]): Promise<CreatedApiKey> {
  return post('/api/auth/keys', { name, scopes });
}

export function revokeApiKey(keyId: string): Promise<null> {
  return del(`/api/auth/keys/${encodeURIComponent(keyId)}`);
}
