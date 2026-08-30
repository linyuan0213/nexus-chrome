/** 会话状态。 */

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import * as api from '@/api/sessions';
import type { CreateSessionRequest, SessionInfo } from '@/api/types';

export const useSessionsStore = defineStore('sessions', () => {
  const sessions = ref<SessionInfo[]>([]);
  const recovered = ref<Array<Record<string, unknown>>>([]);
  const loading = ref(false);
  const error = ref('');

  const count = computed(() => sessions.value.length);

  async function fetchAll(): Promise<void> {
    loading.value = true;
    error.value = '';
    try {
      const data = await api.listSessions();
      sessions.value = data.sessions ?? [];
      recovered.value = data.recovered ?? [];
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  async function create(req: CreateSessionRequest): Promise<SessionInfo> {
    const session = await api.createSession(req);
    await fetchAll();
    return session;
  }

  async function remove(id: string): Promise<void> {
    await api.deleteSession(id);
    sessions.value = sessions.value.filter((s) => s.id !== id);
  }

  /** WS 事件驱动的局部刷新。 */
  function onSessionEvent(type: string, id: string): void {
    if (type === 'session_deleted') {
      sessions.value = sessions.value.filter((s) => s.id !== id);
    } else if (type === 'session_created') {
      void fetchAll();
    }
  }

  return { sessions, recovered, loading, error, count, fetchAll, create, remove, onSessionEvent };
});
