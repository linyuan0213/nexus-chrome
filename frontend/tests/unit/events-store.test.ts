import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it } from 'vitest';

import { MAX_EVENTS, useEventsStore } from '@/stores/events';

describe('events store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('push 将事件插入头部', () => {
    const store = useEventsStore();
    store.push({ type: 'session_created', data: { id: 'a' } });
    store.push({ type: 'session_deleted', data: { id: 'b' } });
    expect(store.events).toHaveLength(2);
    expect(store.events[0].type).toBe('session_deleted');
    expect(store.events[1].type).toBe('session_created');
  });

  it('ping 心跳不入缓冲', () => {
    const store = useEventsStore();
    store.push({ type: 'ping' });
    expect(store.events).toHaveLength(0);
  });

  it('环形缓冲不超过上限', () => {
    const store = useEventsStore();
    for (let i = 0; i < MAX_EVENTS + 50; i++) {
      store.push({ type: 'session_created', data: { id: String(i) } });
    }
    expect(store.events).toHaveLength(MAX_EVENTS);
    expect(store.events[0].data?.id).toBe(String(MAX_EVENTS + 49));
  });

  it('暂停时事件被丢弃', () => {
    const store = useEventsStore();
    store.setPaused(true);
    store.push({ type: 'session_created', data: { id: 'x' } });
    expect(store.events).toHaveLength(0);
    store.setPaused(false);
    store.push({ type: 'session_created', data: { id: 'y' } });
    expect(store.events).toHaveLength(1);
  });

  it('clear 清空缓冲', () => {
    const store = useEventsStore();
    store.push({ type: 'session_created', data: { id: 'a' } });
    store.clear();
    expect(store.events).toHaveLength(0);
  });
});
