<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NInput, NModal, NStatistic, useDialog, useMessage } from 'naive-ui';
import { computed, ref } from 'vue';

import EmptyState from '@/components/common/EmptyState.vue';
import StatusBadge from '@/components/common/StatusBadge.vue';
import { vncPageUrl, vncUrl } from '@/composables/useVncUrl';
import { useInstancesStore } from '@/stores/instances';
import { usePolling } from '@/composables/usePolling';
import { useAppStore } from '@/stores/app';
import type { InstanceInfo } from '@/api/types';
import { restartInstance } from '@/api/instances';

const store = useInstancesStore();
const appStore = useAppStore();
const dialog = useDialog();
const message = useMessage();

usePolling(
  () => store.fetchAll(),
  () => appStore.pollInterval,
);

const vncTarget = ref<InstanceInfo | null>(null);
const vncPassword = ref('');

const vncIframeSrc = computed(() =>
  vncTarget.value ? vncUrl(vncTarget.value.display, vncPassword.value || undefined) : '',
);

function idleText(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function confirmClose(inst: InstanceInfo): void {
  const action = inst.alive ? '关闭' : '移除';
  dialog.warning({
    title: `${action}实例`,
    content: inst.alive
      ? `确定关闭实例 ${inst.key}？其上的会话将无法继续使用。`
      : `实例 ${inst.key} 已停止，移除其记录？（已停止的实例会在下次会话使用时自动重建）`,
    positiveText: action,
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await store.close(inst.key);
        message.success(`实例 ${inst.key} 已${action}`);
      } catch (e) {
        message.error(e instanceof Error ? e.message : String(e));
      }
    },
  });
}

function openVnc(inst: InstanceInfo): void {
  vncPassword.value = appStore.effectiveVncPassword;
  vncTarget.value = inst;
}

const restartingKey = ref('');

async function restart(inst: InstanceInfo): Promise<void> {
  restartingKey.value = inst.key;
  try {
    await restartInstance(inst.key);
    message.success(`实例 ${inst.key} 已启动`);
    await store.fetchAll();
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    restartingKey.value = '';
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center gap-2">
      <h2 class="text-lg font-medium">浏览器实例</h2>
      <NButton
        size="small"
        quaternary
        aria-label="刷新实例"
        :loading="store.loading"
        @click="store.fetchAll()"
      >
        <Icon icon="lucide:refresh-cw" />
      </NButton>
    </div>

    <EmptyState
      v-if="!store.loading && store.instances.length === 0"
      icon="lucide:server"
      title="暂无运行实例"
      description="创建会话后实例将按需启动"
    />

    <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <NCard v-for="inst in store.instances" :key="inst.key" size="small">
        <div class="flex items-center justify-between">
          <span class="font-mono font-medium">{{ inst.key }}</span>
          <StatusBadge :status="inst.alive ? 'success' : 'error'" :text="inst.alive ? '运行中' : '已停止'" />
        </div>
        <p v-if="!inst.alive" class="mt-1 text-xs text-muted-foreground">
          已停止的实例会在下次会话使用时自动拉起
        </p>

        <div class="mt-3 grid grid-cols-3 gap-2 text-center">
          <NStatistic label="CDP 端口" :value="inst.port" />
          <NStatistic label="引用数" :value="inst.ref_count" />
          <NStatistic label="空闲" :value="idleText(inst.idle_seconds)" />
        </div>

        <div v-if="inst.display" class="mt-3 text-xs text-muted-foreground">
          Display {{ inst.display }} · VNC :{{ inst.vnc_port }} · Web :{{ inst.web_port }}
        </div>

        <div class="mt-3 flex gap-2">
          <NButton v-if="inst.display" size="small" tag="a" :href="vncPageUrl(inst.display)" target="_blank">
            <template #icon><Icon icon="lucide:external-link" /></template>
            VNC
          </NButton>
          <NButton v-if="inst.display" size="small" secondary @click="openVnc(inst)">
            <template #icon><Icon icon="lucide:monitor" /></template>
            内嵌查看
          </NButton>
          <NButton
            v-if="!inst.alive"
            size="small"
            type="primary"
            :loading="restartingKey === inst.key"
            @click="restart(inst)"
          >
            <template #icon><Icon icon="lucide:play" /></template>
            启动
          </NButton>
          <NButton
            size="small"
            type="error"
            secondary
            :disabled="inst.key === 'default'"
            @click="confirmClose(inst)"
          >
            <template #icon><Icon :icon="inst.alive ? 'lucide:power' : 'lucide:trash-2'" /></template>
            {{ inst.alive ? '关闭' : '移除' }}
          </NButton>
        </div>
      </NCard>
    </div>

    <NModal
      :show="vncTarget !== null"
      preset="card"
      :title="`实例 ${vncTarget?.key} — VNC`"
      class="w-[95vw] max-w-5xl"
      @update:show="vncTarget = null"
    >
      <NInput
        v-model:value="vncPassword"
        type="password"
        placeholder="VNC 密码（VNC_PASSWORD，可留空尝试无密码连接）"
        class="mb-2"
        aria-label="VNC 密码"
      />
      <iframe
        v-if="vncTarget"
        :src="vncIframeSrc"
        class="h-[70vh] w-full rounded-md border border-border bg-card"
        title="noVNC 浏览器视图"
        allow="clipboard-read; clipboard-write"
      />
    </NModal>
  </div>
</template>
