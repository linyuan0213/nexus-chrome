<script setup lang="ts">
import { NButton, NDynamicTags, NModal, NSlider, useMessage } from 'naive-ui';
import { ref, watch } from 'vue';

import * as api from '@/api/profiles';
import type { RolloutRule } from '@/api/types';

const props = defineProps<{ profileId: string; rollout?: RolloutRule }>();
const emit = defineEmits<{ published: [] }>();

const show = defineModel<boolean>('show', { required: true });

const message = useMessage();
const percent = ref(100);
const nodes = ref<string[]>([]);
const loading = ref(false);

watch(show, (v) => {
  if (v) {
    percent.value = props.rollout?.percent ?? 100;
    nodes.value = [...(props.rollout?.nodes ?? [])];
  }
});

async function submit(): Promise<void> {
  loading.value = true;
  try {
    await api.grayPublish(props.profileId, { percent: percent.value, nodes: nodes.value });
    message.success('灰度规则已更新');
    show.value = false;
    emit('published');
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <NModal :show="show" preset="card" title="灰度发布" class="w-[95vw] max-w-md" @update:show="show = $event">
    <div class="space-y-4">
      <div>
        <label class="mb-1 block text-sm">按节点哈希灰度：{{ percent }}%</label>
        <NSlider v-model:value="percent" :min="0" :max="100" :step="5" />
      </div>
      <div>
        <label class="mb-1 block text-sm">显式节点列表（命中即生效）</label>
        <NDynamicTags v-model:value="nodes" />
      </div>
    </div>
    <template #footer>
      <div class="flex justify-end gap-2">
        <NButton @click="show = false">取消</NButton>
        <NButton type="primary" :loading="loading" @click="submit">发布</NButton>
      </div>
    </template>
  </NModal>
</template>
