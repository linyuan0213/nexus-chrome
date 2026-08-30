/** WebSocket 事件流状态：环形缓冲 + 连接状态。 */

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import type { WsEvent } from '@/api/types';

export const MAX_EVENTS = 500;

export interface StoredEvent extends WsEvent {
  _receivedAt: number;
}

export const useEventsStore = defineStore('events', () => {
  const events = ref<StoredEvent[]>([]);
  const connected = ref(false);
  const paused = ref(false);

  const unreadCount = computed(() => events.value.length);

  function push(event: WsEvent): void {
    if (event.type === 'ping') return;
    if (paused.value) return;
    events.value.unshift({ ...event, _receivedAt: Date.now() });
    if (events.value.length > MAX_EVENTS) {
      events.value.length = MAX_EVENTS;
    }
  }

  function clear(): void {
    events.value = [];
  }

  function setPaused(value: boolean): void {
    paused.value = value;
  }

  function setConnected(value: boolean): void {
    connected.value = value;
  }

  return { events, connected, paused, unreadCount, push, clear, setPaused, setConnected };
});
