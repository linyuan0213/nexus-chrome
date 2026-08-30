/** 可暂停轮询：页面不可见时自动暂停。 */

import { onBeforeUnmount, onMounted, ref } from 'vue';

export function usePolling(fn: () => void | Promise<void>, intervalMs: () => number) {
  const active = ref(false);
  let timer: ReturnType<typeof setInterval> | null = null;

  function stop(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
    active.value = false;
  }

  function start(): void {
    stop();
    active.value = true;
    void fn();
    timer = setInterval(() => {
      if (document.visibilityState === 'visible') void fn();
    }, intervalMs());
  }

  onMounted(start);
  onBeforeUnmount(stop);

  return { active, start, stop };
}
