<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NInput, NInputNumber, NSelect, useMessage } from 'naive-ui';
import { computed, onMounted, ref } from 'vue';

import * as api from '@/api/sessions';
import EmptyState from '@/components/common/EmptyState.vue';
import JsonViewer from '@/components/common/JsonViewer.vue';
import { useSessionsStore } from '@/stores/sessions';

const sessionsStore = useSessionsStore();
const message = useMessage();

const sessionId = ref<string | null>(null);
const operation = ref<'fetch' | 'request' | 'm3u8' | 'download'>('fetch');
const url = ref('');
const timeout = ref(60);
const loading = ref(false);
const result = ref<unknown>(undefined);

const opOptions = [
  { label: 'fetch — 纯 HTTP 请求', value: 'fetch' },
  { label: 'request — 聚合请求（自动过盾）', value: 'request' },
  { label: 'm3u8 — 播放列表探测', value: 'm3u8' },
  { label: 'download — 浏览器下载', value: 'download' },
];

const sessionOptions = computed(() => sessionsStore.sessions.map((s) => ({ label: s.id, value: s.id })));

const downloadData = computed(() => {
  const r = result.value as Record<string, unknown> | undefined;
  if (operation.value !== 'download' || !r) return null;
  const b64 = (r.base64 ?? r.data) as string | undefined;
  if (!b64) return null;
  return { base64: b64, filename: (r.filename as string) ?? 'download.bin' };
});

function saveDownload(): void {
  if (!downloadData.value) return;
  const a = document.createElement('a');
  a.href = `data:application/octet-stream;base64,${downloadData.value.base64}`;
  a.download = downloadData.value.filename;
  a.click();
}

async function send(): Promise<void> {
  if (!sessionId.value) {
    message.warning('请选择会话');
    return;
  }
  if (!url.value.trim()) {
    message.warning('请输入 URL');
    return;
  }
  loading.value = true;
  result.value = undefined;
  const id = sessionId.value;
  const u = url.value.trim();
  try {
    switch (operation.value) {
      case 'fetch':
        result.value = await api.httpFetch(id, { url: u, timeout: timeout.value });
        break;
      case 'request':
        result.value = await api.unifiedRequest(id, { url: u, timeout: timeout.value });
        break;
      case 'm3u8':
        result.value = await api.detectM3u8(id, { url: u, timeout: timeout.value });
        break;
      case 'download':
        result.value = await api.download(id, { url: u, timeout: timeout.value });
        break;
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  if (!sessionsStore.sessions.length) void sessionsStore.fetchAll();
});
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-4">
    <NCard size="small" title="请求调试台">
      <div class="space-y-3">
        <div class="flex flex-wrap gap-2">
          <NSelect
            v-model:value="sessionId"
            :options="sessionOptions"
            placeholder="选择会话"
            class="w-48"
            aria-label="选择会话"
          />
          <NSelect v-model:value="operation" :options="opOptions" class="w-64" aria-label="操作类型" />
          <NInputNumber v-model:value="timeout" :min="5" :max="600" class="w-28" aria-label="超时秒数" />
        </div>
        <div class="flex gap-2">
          <NInput
            v-model:value="url"
            placeholder="https://example.com/…"
            aria-label="目标 URL"
            @keyup.enter="send"
          />
          <NButton type="primary" :loading="loading" @click="send">
            <template #icon><Icon icon="lucide:send" /></template>
            发送
          </NButton>
        </div>
      </div>
    </NCard>

    <NCard v-if="result !== undefined" size="small" title="响应">
      <template v-if="downloadData" #header-extra>
        <NButton size="small" @click="saveDownload">
          <template #icon><Icon icon="lucide:download" /></template>
          保存文件
        </NButton>
      </template>
      <JsonViewer :data="result" max-height="32rem" />
    </NCard>

    <EmptyState
      v-else
      icon="lucide:terminal"
      title="选择会话并发起请求"
      description="支持 fetch / 自动过盾 request / m3u8 探测 / 浏览器下载"
    />
  </div>
</template>
