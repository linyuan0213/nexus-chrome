<script setup lang="ts">
import { NButton, NInput, NModal, useMessage } from 'naive-ui';
import { ref } from 'vue';

import * as api from '@/api/sessions';

const props = defineProps<{ sessionId: string }>();
const show = defineModel<boolean>('show', { required: true });

const message = useMessage();
const proxy = ref('');
const loading = ref(false);

async function submit(): Promise<void> {
  if (!proxy.value.trim()) {
    message.warning('请输入代理地址');
    return;
  }
  loading.value = true;
  try {
    await api.setProxy(props.sessionId, { proxy: proxy.value.trim() });
    message.success('代理已切换');
    show.value = false;
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <NModal :show="show" preset="card" title="切换代理" class="w-[95vw] max-w-md" @update:show="show = $event">
    <NInput
      v-model:value="proxy"
      placeholder="http://user:pass@host:port 或 socks5://host:port"
      aria-label="代理地址"
      @keyup.enter="submit"
    />
    <template #footer>
      <div class="flex justify-end gap-2">
        <NButton @click="show = false">取消</NButton>
        <NButton type="primary" :loading="loading" @click="submit">切换</NButton>
      </div>
    </template>
  </NModal>
</template>
