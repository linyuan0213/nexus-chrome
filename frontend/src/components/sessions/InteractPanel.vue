<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NInput, NInputNumber, NSwitch, useMessage } from 'naive-ui';
import { ref } from 'vue';

import * as api from '@/api/sessions';
import CodeEditor from '@/components/common/CodeEditor.vue';
import JsonViewer from '@/components/common/JsonViewer.vue';

const props = defineProps<{ sessionId: string }>();
const message = useMessage();

// 点击
const clickSelector = ref('');
const clickHumanize = ref(true);
const clickLoading = ref(false);

// 拖拽
const dragSelector = ref('');
const dragX = ref(100);
const dragY = ref(0);
const dragDuration = ref(1.0);
const dragLoading = ref(false);

// 输入
const inputSelector = ref('');
const inputValue = ref('');
const inputLoading = ref(false);

// JS
const script = ref('');
const jsLoading = ref(false);
const jsResult = ref<unknown>(undefined);

async function run(fn: () => Promise<unknown>, loading: { value: boolean }, ok: string): Promise<void> {
  loading.value = true;
  try {
    await fn();
    message.success(ok);
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}

async function doClick(): Promise<void> {
  await run(
    () => api.click(props.sessionId, { selector: clickSelector.value, humanize: clickHumanize.value }),
    clickLoading,
    `已点击 ${clickSelector.value}`,
  );
}

async function doDrag(): Promise<void> {
  await run(
    () =>
      api.drag(props.sessionId, {
        selector: dragSelector.value,
        offset_x: dragX.value,
        offset_y: dragY.value,
        duration: dragDuration.value,
      }),
    dragLoading,
    '拖拽完成',
  );
}

async function doInput(): Promise<void> {
  await run(
    () => api.inputText(props.sessionId, { selector: inputSelector.value, text: inputValue.value }),
    inputLoading,
    '已输入',
  );
}

async function doExecute(): Promise<void> {
  jsLoading.value = true;
  jsResult.value = undefined;
  try {
    const res = await api.executeJs(props.sessionId, { script: script.value });
    jsResult.value = res.result;
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    jsLoading.value = false;
  }
}
</script>

<template>
  <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
    <NCard size="small" title="点击元素">
      <div class="space-y-2">
        <NInput v-model:value="clickSelector" placeholder="CSS 选择器或 XPath" aria-label="点击选择器" />
        <div class="flex items-center justify-between">
          <label class="flex items-center gap-1.5 text-sm">
            <NSwitch v-model:value="clickHumanize" size="small" />
            人性化轨迹
          </label>
          <NButton size="small" :loading="clickLoading" :disabled="!clickSelector" @click="doClick">
            <template #icon><Icon icon="lucide:mouse-pointer-click" /></template>
            点击
          </NButton>
        </div>
      </div>
    </NCard>

    <NCard size="small" title="拖拽（滑块验证码）">
      <div class="space-y-2">
        <NInput v-model:value="dragSelector" placeholder="滑块选择器" aria-label="拖拽选择器" />
        <div class="grid grid-cols-3 gap-2">
          <div>
            <label class="mb-1 block text-xs text-muted-foreground" for="drag-x">水平偏移 (px)</label>
            <NInputNumber id="drag-x" v-model:value="dragX" :show-button="false" class="w-full" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-muted-foreground" for="drag-y">垂直偏移 (px)</label>
            <NInputNumber id="drag-y" v-model:value="dragY" :show-button="false" class="w-full" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-muted-foreground" for="drag-duration">时长 (秒)</label>
            <NInputNumber
              id="drag-duration"
              v-model:value="dragDuration"
              :step="0.1"
              :min="0.1"
              :show-button="false"
              class="w-full"
            />
          </div>
        </div>
        <div class="flex justify-end">
          <NButton size="small" :loading="dragLoading" :disabled="!dragSelector" @click="doDrag">
            <template #icon><Icon icon="lucide:move-horizontal" /></template>
            拖拽
          </NButton>
        </div>
      </div>
    </NCard>

    <NCard size="small" title="输入文本">
      <div class="space-y-2">
        <NInput v-model:value="inputSelector" placeholder="输入框选择器" aria-label="输入选择器" />
        <div class="flex gap-2">
          <NInput v-model:value="inputValue" placeholder="文本" @keyup.enter="doInput" />
          <NButton size="small" :loading="inputLoading" :disabled="!inputSelector" @click="doInput">
            <template #icon><Icon icon="lucide:keyboard" /></template>
            输入
          </NButton>
        </div>
      </div>
    </NCard>

    <NCard size="small" title="执行 JavaScript">
      <div class="space-y-2">
        <CodeEditor v-model="script" placeholder="return document.title" :rows="4" />
        <div class="flex justify-end">
          <NButton size="small" :loading="jsLoading" :disabled="!script.trim()" @click="doExecute">
            <template #icon><Icon icon="lucide:play" /></template>
            运行
          </NButton>
        </div>
        <JsonViewer v-if="jsResult !== undefined" :data="jsResult" max-height="12rem" />
      </div>
    </NCard>
  </div>
</template>
