<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NInput, NTag, useMessage } from 'naive-ui';
import { onMounted, ref } from 'vue';

import * as api from '@/api/sessions';
import type { TabInfo } from '@/api/types';

const props = defineProps<{ sessionId: string }>();
const emit = defineEmits<{ changed: [] }>();

const message = useMessage();
const tabs = ref<TabInfo[]>([]);
const activeTab = ref<string | null>(null);
const newTabName = ref('');
const newTabUrl = ref('');
const loading = ref(false);

async function refresh(): Promise<void> {
  try {
    const data = await api.listTabs(props.sessionId);
    tabs.value = data.tabs ?? [];
    activeTab.value = data.active ?? null;
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  }
}

async function create(): Promise<void> {
  loading.value = true;
  try {
    await api.createTab(props.sessionId, newTabName.value || undefined, newTabUrl.value || undefined);
    newTabName.value = '';
    newTabUrl.value = '';
    await refresh();
    emit('changed');
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}

async function switchTo(name: string): Promise<void> {
  try {
    await api.switchTab(props.sessionId, name);
    await refresh();
    emit('changed');
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  }
}

async function close(name: string): Promise<void> {
  try {
    await api.closeTab(props.sessionId, name);
    await refresh();
    emit('changed');
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  }
}

onMounted(refresh);
defineExpose({ refresh });
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap gap-1.5" role="tablist" aria-label="标签页列表">
      <NTag
        v-for="t in tabs"
        :key="t.name"
        :type="t.name === activeTab ? 'primary' : 'default'"
        closable
        class="cursor-pointer"
        @click="switchTo(String(t.name))"
        @close.stop="close(String(t.name))"
      >
        {{ t.name }}
      </NTag>
      <span v-if="!tabs.length" class="text-sm text-muted-foreground">暂无标签页</span>
    </div>
    <div class="flex flex-wrap gap-2">
      <NInput v-model:value="newTabName" placeholder="标签名（可选）" class="w-36" aria-label="新标签名" />
      <NInput
        v-model:value="newTabUrl"
        placeholder="初始 URL（可选）"
        class="min-w-40 flex-1"
        aria-label="新标签 URL"
        @keyup.enter="create"
      />
      <NButton size="small" :loading="loading" @click="create">
        <template #icon><Icon icon="lucide:plus" /></template>
        新建
      </NButton>
    </div>
  </div>
</template>
