<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NButtonGroup, NSwitch, useMessage } from 'naive-ui';
import { computed, ref } from 'vue';

import * as api from '@/api/sessions';
import EmptyState from '@/components/common/EmptyState.vue';

const props = defineProps<{ sessionId: string }>();
const emit = defineEmits<{ captured: [] }>();

const message = useMessage();
const fullPage = ref(false);
const loading = ref(false);
const imageData = ref('');

/** 缩放模式：fit=铺满容器宽度，数字=原始尺寸的百分比 */
const zoom = ref<'fit' | number>('fit');

const src = computed(() => (imageData.value ? `data:image/png;base64,${imageData.value}` : ''));

const zoomLabel = computed(() => (zoom.value === 'fit' ? '适应' : `${zoom.value}%`));

const imgStyle = computed(() => {
  if (zoom.value === 'fit') return { width: '100%' };
  return { width: `${zoom.value}%`, maxWidth: 'none' };
});

function zoomIn(): void {
  const current = zoom.value === 'fit' ? 100 : zoom.value;
  zoom.value = Math.min(current + 25, 400);
}

function zoomOut(): void {
  const current = zoom.value === 'fit' ? 100 : zoom.value;
  zoom.value = Math.max(current - 25, 25);
}

function download(): void {
  if (!imageData.value) return;
  const a = document.createElement('a');
  a.href = src.value;
  a.download = `screenshot-${props.sessionId}-${Date.now()}.png`;
  a.click();
}

async function capture(): Promise<void> {
  loading.value = true;
  try {
    const result = await api.screenshot(props.sessionId, undefined, fullPage.value);
    const data = result.png_base64 ?? '';
    if (!data) throw new Error('响应中无截图数据');
    imageData.value = data.startsWith('data:') ? data.split(',')[1] : data;
    zoom.value = 'fit';
    emit('captured');
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}

defineExpose({ capture });
</script>

<template>
  <div class="space-y-2">
    <div class="flex flex-wrap items-center gap-3">
      <NButton size="small" :loading="loading" @click="capture">
        <template #icon><Icon icon="lucide:camera" /></template>
        截图
      </NButton>
      <NButton v-if="src" size="small" secondary @click="download">
        <template #icon><Icon icon="lucide:download" /></template>
        下载
      </NButton>
      <label class="flex items-center gap-1.5 text-sm">
        <NSwitch v-model:value="fullPage" size="small" />
        整页
      </label>

      <template v-if="src">
        <div class="flex-1" />
        <NButtonGroup size="small">
          <NButton aria-label="缩小" :disabled="zoom === 25" @click="zoomOut">
            <Icon icon="lucide:zoom-out" />
          </NButton>
          <NButton aria-label="原始尺寸" @click="zoom = 100">
            <span class="w-12 text-center text-xs">{{ zoomLabel }}</span>
          </NButton>
          <NButton aria-label="放大" :disabled="zoom === 400" @click="zoomIn">
            <Icon icon="lucide:zoom-in" />
          </NButton>
        </NButtonGroup>
        <NButton size="small" quaternary :disabled="zoom === 'fit'" @click="zoom = 'fit'">
          <Icon icon="lucide:maximize" />
        </NButton>
      </template>
    </div>

    <div v-if="src" class="max-h-[60vh] overflow-auto rounded-md border border-border bg-card">
      <img :src="src" alt="页面截图" :style="imgStyle" class="block" />
    </div>
    <EmptyState v-else icon="lucide:image" title="暂无截图" description="导航后点击截图查看页面" />
  </div>
</template>
