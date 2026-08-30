/** 浏览器实例池状态。 */

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import * as api from '@/api/instances';
import type { InstanceInfo } from '@/api/types';

export const useInstancesStore = defineStore('instances', () => {
  const instances = ref<InstanceInfo[]>([]);
  const loading = ref(false);
  const error = ref('');

  const aliveCount = computed(() => instances.value.filter((i) => i.alive).length);

  async function fetchAll(): Promise<void> {
    loading.value = true;
    error.value = '';
    try {
      const data = await api.listInstances();
      instances.value = data.instances ?? [];
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  async function close(key: string): Promise<void> {
    await api.closeInstance(key);
    instances.value = instances.value.filter((i) => i.key !== key);
  }

  return { instances, loading, error, aliveCount, fetchAll, close };
});
