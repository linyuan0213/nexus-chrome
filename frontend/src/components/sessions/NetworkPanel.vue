<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NInput, NInputNumber, NSelect, NSwitch, useMessage } from 'naive-ui';
import { ref } from 'vue';

import * as api from '@/api/sessions';
import JsonViewer from '@/components/common/JsonViewer.vue';

const props = defineProps<{ sessionId: string }>();
const message = useMessage();

const mode = ref<'fetch' | 'request'>('fetch');
const url = ref('');
const method = ref('GET');
const body = ref('');
const timeout = ref(30);
const navigateIfChallenge = ref(true);
const returnHtml = ref(false);
const loading = ref(false);
const result = ref<unknown>(undefined);

const methodOptions = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'].map((m) => ({ label: m, value: m }));

async function send(): Promise<void> {
  if (!url.value.trim()) {
    message.warning('请输入 URL');
    return;
  }
  loading.value = true;
  result.value = undefined;
  try {
    let data: unknown = undefined;
    if (body.value.trim()) {
      try {
        data = JSON.parse(body.value);
      } catch {
        data = body.value;
      }
    }
    if (mode.value === 'fetch') {
      result.value = await api.httpFetch(props.sessionId, {
        url: url.value.trim(),
        method: method.value,
        data,
        timeout: timeout.value,
      });
    } else {
      result.value = await api.unifiedRequest(props.sessionId, {
        url: url.value.trim(),
        method: method.value,
        data,
        timeout: timeout.value,
        navigate_if_challenge: navigateIfChallenge.value,
        return_html: returnHtml.value,
      });
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap gap-2">
      <NSelect
        v-model:value="mode"
        :options="[
          { label: 'fetch（纯 HTTP）', value: 'fetch' },
          { label: 'request（自动过盾）', value: 'request' },
        ]"
        class="w-48"
        aria-label="请求模式"
      />
      <NSelect v-model:value="method" :options="methodOptions" class="w-28" aria-label="HTTP 方法" />
      <NInputNumber v-model:value="timeout" :min="5" :max="300" class="w-28" aria-label="超时秒数" />
    </div>
    <NInput
      v-model:value="url"
      placeholder="https://example.com/api"
      aria-label="请求 URL"
      @keyup.enter="send"
    />
    <NInput
      v-if="method !== 'GET' && method !== 'HEAD'"
      v-model:value="body"
      type="textarea"
      :rows="3"
      placeholder="请求体（JSON 或文本）"
      class="font-mono text-xs"
    />
    <div v-if="mode === 'request'" class="flex items-center gap-4 text-sm">
      <label class="flex items-center gap-1.5">
        <NSwitch v-model:value="navigateIfChallenge" size="small" />
        命中挑战时过盾
      </label>
      <label class="flex items-center gap-1.5">
        <NSwitch v-model:value="returnHtml" size="small" />
        返回渲染后 HTML
      </label>
    </div>
    <div>
      <NButton type="primary" size="small" :loading="loading" @click="send">
        <template #icon><Icon icon="lucide:send" /></template>
        发送
      </NButton>
    </div>
    <JsonViewer v-if="result !== undefined" :data="result" />
  </div>
</template>
