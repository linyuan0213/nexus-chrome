<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NGrid, NGi, NStatistic } from 'naive-ui';
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';

import StatusBadge from '@/components/common/StatusBadge.vue';
import { useAppStore } from '@/stores/app';
import { useEventsStore } from '@/stores/events';
import { useInstancesStore } from '@/stores/instances';
import { useSessionsStore } from '@/stores/sessions';
import dayjs from 'dayjs';

const router = useRouter();
const appStore = useAppStore();
const sessionsStore = useSessionsStore();
const instancesStore = useInstancesStore();
const eventsStore = useEventsStore();

onMounted(() => {
  void sessionsStore.fetchAll();
  void instancesStore.fetchAll();
});
</script>

<template>
  <div class="space-y-4">
    <NGrid :cols="2" :x-gap="12" :y-gap="12" responsive="screen" item-responsive>
      <NGi span="2 m:1">
        <NCard size="small">
          <NStatistic label="运行会话">
            <span class="text-3xl font-semibold">{{ sessionsStore.count }}</span>
          </NStatistic>
        </NCard>
      </NGi>
      <NGi span="2 m:1">
        <NCard size="small">
          <NStatistic label="浏览器实例">
            <span class="text-3xl font-semibold">{{ instancesStore.aliveCount }}</span>
            <span class="text-sm text-muted-foreground"> / {{ instancesStore.instances.length }}</span>
          </NStatistic>
        </NCard>
      </NGi>
    </NGrid>

    <NCard size="small" title="服务信息">
      <div class="flex flex-wrap items-center gap-3">
        <StatusBadge
          :status="appStore.statusError ? 'error' : 'success'"
          :text="appStore.statusError ? '离线' : '运行中'"
        />
        <span v-if="appStore.status" class="text-sm text-muted-foreground">
          版本 {{ appStore.status.version }} · 浏览器 {{ appStore.status.browser }}
        </span>
        <div class="flex-1" />
        <NButton size="small" @click="router.push({ name: 'sessions', query: { create: '1' } })">
          <template #icon><Icon icon="lucide:plus" /></template>
          新建会话
        </NButton>
        <NButton size="small" secondary @click="router.push({ name: 'profiles' })">
          <template #icon><Icon icon="lucide:fingerprint" /></template>
          管理画像
        </NButton>
      </div>
    </NCard>

    <NCard size="small" title="最近事件">
      <ul v-if="eventsStore.events.length" class="divide-y divide-border" role="list">
        <li
          v-for="(e, i) in eventsStore.events.slice(0, 10)"
          :key="e._receivedAt + '-' + i"
          class="flex items-center gap-2 py-1.5 text-sm"
        >
          <StatusBadge
            :status="e.type.includes('created') ? 'success' : e.type.includes('deleted') ? 'error' : 'info'"
            :text="e.type"
          />
          <span class="font-mono text-xs">{{ e.data?.id ?? '' }}</span>
          <span class="ml-auto text-xs text-muted-foreground">
            {{ dayjs(e._receivedAt).format('HH:mm:ss') }}
          </span>
        </li>
      </ul>
      <p v-else class="py-4 text-center text-sm text-muted-foreground">
        暂无事件 · 事件流{{ eventsStore.connected ? '已连接' : '未连接' }}
      </p>
    </NCard>
  </div>
</template>
