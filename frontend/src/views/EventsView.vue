<script setup lang="ts">
import { NButton, NCard, NSelect } from 'naive-ui';
import dayjs from 'dayjs';
import { computed, ref } from 'vue';

import EmptyState from '@/components/common/EmptyState.vue';
import JsonViewer from '@/components/common/JsonViewer.vue';
import StatusBadge from '@/components/common/StatusBadge.vue';
import { useEventsStore } from '@/stores/events';

const eventsStore = useEventsStore();
const typeFilter = ref<string | null>(null);

const eventTypes = computed(() => {
  const types = new Set(eventsStore.events.map((e) => e.type));
  return [...types].map((t) => ({ label: t, value: t }));
});

const filtered = computed(() =>
  typeFilter.value ? eventsStore.events.filter((e) => e.type === typeFilter.value) : eventsStore.events,
);

function badgeStatus(type: string): 'success' | 'error' | 'info' | 'default' {
  if (type.includes('created')) return 'success';
  if (type.includes('deleted') || type.includes('error')) return 'error';
  if (type.includes('challenge')) return 'info';
  return 'default';
}
</script>

<template>
  <NCard size="small">
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <NSelect
        v-model:value="typeFilter"
        :options="eventTypes"
        clearable
        placeholder="全部类型"
        class="w-48"
        aria-label="事件类型过滤"
      />
      <NButton size="small" @click="eventsStore.setPaused(!eventsStore.paused)">
        {{ eventsStore.paused ? '继续' : '暂停' }}
      </NButton>
      <NButton size="small" @click="eventsStore.clear()">清空</NButton>
      <span class="ml-auto text-sm text-muted-foreground">
        {{ filtered.length }} 条 · {{ eventsStore.connected ? '已连接' : '已断开' }}
      </span>
    </div>

    <EmptyState
      v-if="filtered.length === 0"
      icon="lucide:activity"
      title="暂无事件"
      description="会话创建/删除等事件将实时推送到这里"
    />

    <ul v-else class="divide-y divide-border" role="list">
      <li v-for="(e, i) in filtered" :key="e._receivedAt + '-' + i" class="py-2">
        <div class="flex items-center gap-2">
          <StatusBadge :status="badgeStatus(e.type)" :text="e.type" />
          <span class="text-xs text-muted-foreground">
            {{ dayjs(e._receivedAt).format('HH:mm:ss') }}
          </span>
        </div>
        <JsonViewer
          v-if="e.data && Object.keys(e.data).length"
          :data="e.data"
          max-height="10rem"
          class="mt-1"
        />
      </li>
    </ul>
  </NCard>
</template>
