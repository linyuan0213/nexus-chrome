<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCollapse, NCollapseItem, NInput, NInputNumber, useMessage } from 'naive-ui';
import { ref } from 'vue';

import * as api from '@/api/sessions';
import type { NavigateResult } from '@/api/types';
import StatusBadge from '@/components/common/StatusBadge.vue';

const props = defineProps<{ sessionId: string }>();
const emit = defineEmits<{ navigated: [result: NavigateResult] }>();

const message = useMessage();
const url = ref('');
const timeout = ref(60);
const cookie = ref('');
const referer = ref('');
const showAdvanced = ref<string[]>([]);
const loading = ref(false);
const lastResult = ref<NavigateResult | null>(null);

async function go(): Promise<void> {
  if (!url.value.trim()) {
    message.warning('请输入 URL');
    return;
  }
  loading.value = true;
  lastResult.value = null;
  try {
    const result = await api.navigate(props.sessionId, {
      url: url.value.trim(),
      timeout: timeout.value,
      cookie: cookie.value.trim() || null,
      referer: referer.value.trim() || null,
    });
    lastResult.value = result;
    emit('navigated', result);
    message.success('导航完成');
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex gap-2">
      <NInput v-model:value="url" placeholder="https://example.com" aria-label="导航 URL" @keyup.enter="go">
        <template #prefix><Icon icon="lucide:globe" /></template>
      </NInput>
      <NInputNumber v-model:value="timeout" :min="5" :max="300" class="w-28" aria-label="超时秒数" />
      <NButton type="primary" :loading="loading" @click="go">
        {{ loading ? '过盾中…' : '导航' }}
      </NButton>
    </div>

    <NCollapse v-model:expanded-names="showAdvanced" class="advanced-collapse">
      <NCollapseItem name="advanced">
        <template #header>
          <span class="text-xs text-muted-foreground">高级选项（Cookie / Referer）</span>
        </template>
        <div class="space-y-2 pt-1">
          <div>
            <label class="mb-1 block text-xs text-muted-foreground" for="nav-cookie">
              携带 Cookie（格式：name=value; name2=value2）
            </label>
            <NInput
              id="nav-cookie"
              v-model:value="cookie"
              placeholder="留空则自动携带该域名已存储的 Cookie"
              size="small"
              class="font-mono text-xs"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs text-muted-foreground" for="nav-referer">Referer</label>
            <NInput
              id="nav-referer"
              v-model:value="referer"
              placeholder="https://example.com/"
              size="small"
            />
          </div>
        </div>
      </NCollapseItem>
    </NCollapse>

    <div v-if="lastResult" class="flex flex-wrap items-center gap-2 text-sm">
      <template v-if="lastResult.challenge">
        <StatusBadge
          :status="
            lastResult.challenge.solved ? 'success' : lastResult.challenge.detected ? 'error' : 'default'
          "
          :text="
            lastResult.challenge.detected
              ? lastResult.challenge.solved
                ? `挑战已通过${lastResult.challenge.type ? ` (${lastResult.challenge.type})` : ''}`
                : '挑战未通过'
              : '无挑战'
          "
        />
      </template>
      <span v-if="lastResult.url" class="truncate text-xs text-muted-foreground">{{ lastResult.url }}</span>
    </div>
  </div>
</template>

<style scoped>
.advanced-collapse :deep(.n-collapse-item__header) {
  padding: 4px 0;
}
</style>
