/** /ws/events 全局事件流：自动重连 + 分发到各 store。 */

import { useWebSocket } from '@vueuse/core';
import { watch } from 'vue';

import { wsEventsUrl } from '@/api/client';
import type { WsEvent } from '@/api/types';
import { useEventsStore } from '@/stores/events';
import { useSessionsStore } from '@/stores/sessions';

let started = false;

export function useEventStream(): void {
  if (started) return;
  started = true;

  const eventsStore = useEventsStore();
  const sessionsStore = useSessionsStore();

  const { status, data } = useWebSocket(wsEventsUrl(), {
    autoReconnect: { retries: () => true, delay: 3000 },
    heartbeat: false,
  });

  watch(status, (s) => eventsStore.setConnected(s === 'OPEN'), { immediate: true });

  watch(data, (raw) => {
    if (!raw || typeof raw !== 'string') return;
    let event: WsEvent;
    try {
      event = JSON.parse(raw) as WsEvent;
    } catch {
      return;
    }
    eventsStore.push(event);
    const id = typeof event.data?.id === 'string' ? event.data.id : '';
    if (id && (event.type === 'session_created' || event.type === 'session_deleted')) {
      sessionsStore.onSessionEvent(event.type, id);
    }
  });
}
