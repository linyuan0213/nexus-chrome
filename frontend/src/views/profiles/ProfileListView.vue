<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NInput } from 'naive-ui';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import EmptyState from '@/components/common/EmptyState.vue';
import StatusBadge from '@/components/common/StatusBadge.vue';
import { useProfilesStore } from '@/stores/profiles';

const router = useRouter();
const store = useProfilesStore();
const search = ref('');

onMounted(() => void store.fetchAll());

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return store.profiles;
  return store.profiles.filter(
    (p) => p.profile_id.toLowerCase().includes(q) || (p.name ?? '').toLowerCase().includes(q),
  );
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-2">
      <h2 class="text-lg font-medium">指纹画像</h2>
      <NButton
        size="small"
        quaternary
        aria-label="刷新画像"
        :loading="store.loading"
        @click="store.fetchAll()"
      >
        <Icon icon="lucide:refresh-cw" />
      </NButton>
      <div class="flex-1" />
      <NInput v-model:value="search" placeholder="搜索画像" clearable class="w-56" aria-label="搜索画像">
        <template #prefix><Icon icon="lucide:search" /></template>
      </NInput>
      <NButton type="primary" @click="router.push({ name: 'profile-detail', params: { id: '_new' } })">
        <template #icon><Icon icon="lucide:plus" /></template>
        新建画像
      </NButton>
    </div>

    <p v-if="store.error" class="text-sm text-destructive">{{ store.error }}</p>

    <EmptyState
      v-if="!store.loading && filtered.length === 0"
      icon="lucide:fingerprint"
      title="暂无画像"
      description="创建画像后可在会话中绑定，注入完整浏览器指纹"
      action-text="新建画像"
      @action="router.push({ name: 'profile-detail', params: { id: '_new' } })"
    />

    <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <NCard
        v-for="p in filtered"
        :key="p.profile_id"
        size="small"
        hoverable
        class="cursor-pointer"
        @click="router.push({ name: 'profile-detail', params: { id: p.profile_id } })"
      >
        <div class="flex items-center justify-between">
          <span class="font-mono font-medium">{{ p.profile_id }}</span>
          <StatusBadge
            :status="p.enabled === false ? 'default' : 'success'"
            :text="p.enabled === false ? '已停用' : `v${p.version}`"
          />
        </div>
        <p v-if="p.name" class="mt-1 truncate text-sm">{{ p.name }}</p>
        <div class="mt-2 flex flex-wrap gap-1.5 text-xs">
          <StatusBadge
            v-if="p.rollout && (p.rollout.percent < 100 || p.rollout.nodes.length)"
            status="warning"
            :text="`灰度 ${p.rollout.percent}%`"
          />
          <span v-if="p.updated_at" class="text-muted-foreground">{{ p.updated_at }}</span>
        </div>
      </NCard>
    </div>
  </div>
</template>
