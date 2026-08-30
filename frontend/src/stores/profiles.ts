/** 指纹画像状态。 */

import { defineStore } from 'pinia';
import { ref } from 'vue';

import * as api from '@/api/profiles';
import type { ProfileSummary } from '@/api/types';

export const useProfilesStore = defineStore('profiles', () => {
  const profiles = ref<ProfileSummary[]>([]);
  const loading = ref(false);
  const error = ref('');

  async function fetchAll(): Promise<void> {
    loading.value = true;
    error.value = '';
    try {
      const data = await api.listProfiles();
      profiles.value = data.profiles ?? [];
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  return { profiles, loading, error, fetchAll };
});
