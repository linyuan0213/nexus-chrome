<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, useMessage } from 'naive-ui';
import { computed } from 'vue';

import { copyText } from '@/utils/clipboard';

const props = defineProps<{ data: unknown; maxHeight?: string }>();
const message = useMessage();

const text = computed(() => {
  if (typeof props.data === 'string') return props.data;
  try {
    return JSON.stringify(props.data, null, 2);
  } catch {
    return String(props.data);
  }
});

async function copy(): Promise<void> {
  const ok = await copyText(text.value);
  if (ok) message.success('已复制');
  else message.error('复制失败');
}
</script>

<template>
  <div class="relative">
    <NButton size="tiny" quaternary class="absolute right-1 top-1 z-10" aria-label="复制 JSON" @click="copy">
      <Icon icon="lucide:copy" />
    </NButton>
    <pre
      class="overflow-auto rounded-md border border-border bg-accent p-3 text-xs leading-relaxed"
      :style="{ maxHeight: maxHeight ?? '24rem' }"
    ><code>{{ text }}</code></pre>
  </div>
</template>
