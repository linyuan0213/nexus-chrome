/** 全局应用状态：Token、主题、轮询间隔、服务状态、认证配置。 */

import { defineStore } from 'pinia';
import { computed, ref, watch } from 'vue';

import { getAuthConfig, getAuthMe } from '@/api/auth';
import { getToken, setToken } from '@/api/client';
import * as instancesApi from '@/api/instances';
import type { StatusData } from '@/api/types';

export type ThemeMode = 'light' | 'dark' | 'system';

const THEME_KEY = 'ncm_theme';
const VNC_PASSWORD_KEY = 'ncm_vnc_password';

export const useAppStore = defineStore('app', () => {
  const token = ref(getToken());
  const theme = ref<ThemeMode>((localStorage.getItem(THEME_KEY) as ThemeMode) || 'system');
  const vncPassword = ref(localStorage.getItem(VNC_PASSWORD_KEY) ?? '');
  const pollInterval = ref(10_000);
  const status = ref<StatusData | null>(null);
  const statusError = ref('');
  /** 后端是否开启认证（AUTH_PASSWORD）。null = 未探测。 */
  const authEnabled = ref<boolean | null>(null);
  /** 后端下发的 VNC 配置（/api/auth/me，认证后可见）。 */
  const serverVncPassword = ref('');

  const isDark = computed(() => {
    if (theme.value === 'system') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return theme.value === 'dark';
  });

  /** 生效的 VNC 密码：本地覆盖优先，否则用后端 /api/auth/me 下发的值。 */
  const effectiveVncPassword = computed(() => vncPassword.value || serverVncPassword.value);

  function applyTheme(): void {
    document.documentElement.classList.toggle('dark', isDark.value);
  }

  function setTheme(mode: ThemeMode): void {
    theme.value = mode;
    localStorage.setItem(THEME_KEY, mode);
    applyTheme();
  }

  function saveToken(value: string): void {
    token.value = value.trim();
    setToken(token.value);
  }

  function saveVncPassword(value: string): void {
    vncPassword.value = value;
    if (value) localStorage.setItem(VNC_PASSWORD_KEY, value);
    else localStorage.removeItem(VNC_PASSWORD_KEY);
  }

  /** 探测后端认证配置；已认证时拉取 VNC 等安全配置。 */
  async function checkAuthConfig(): Promise<boolean> {
    try {
      const config = await getAuthConfig();
      authEnabled.value = config.enabled;
    } catch {
      authEnabled.value = false; // 探测失败视为本地模式，不阻塞使用
    }
    if (authEnabled.value === false || token.value) {
      try {
        const me = await getAuthMe();
        serverVncPassword.value = me.vnc_password ?? '';
      } catch {
        // 未认证时 401（由 client 处理跳转登录）
      }
    }
    return authEnabled.value === true;
  }

  async function refreshStatus(): Promise<void> {
    try {
      status.value = await instancesApi.getStatus();
      statusError.value = '';
    } catch (e) {
      statusError.value = e instanceof Error ? e.message : String(e);
      status.value = null;
    }
  }

  watch(theme, applyTheme, { immediate: true });
  if (theme.value === 'system') {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => applyTheme());
  }

  return {
    token,
    theme,
    isDark,
    pollInterval,
    status,
    statusError,
    vncPassword,
    authEnabled,
    serverVncPassword,
    checkAuthConfig,
    effectiveVncPassword,
    setTheme,
    saveToken,
    saveVncPassword,
    refreshStatus,
  };
});
