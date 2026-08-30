<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NInput } from 'naive-ui';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { vncUrl } from '@/composables/useVncUrl';
import { useAppStore } from '@/stores/app';

const props = defineProps<{ display: string | number | null | undefined }>();

const appStore = useAppStore();
const password = ref(appStore.effectiveVncPassword);
const reloadKey = ref(0);
const wrapper = ref<HTMLElement | null>(null);
const isFullscreen = ref(false);

const src = computed(() => {
  void reloadKey.value;
  return vncUrl(props.display, password.value || undefined);
});

function toggleFullscreen(): void {
  if (!wrapper.value) return;
  if (document.fullscreenElement) {
    void document.exitFullscreen();
  } else {
    void wrapper.value.requestFullscreen();
  }
}

function onFullscreenChange(): void {
  isFullscreen.value = document.fullscreenElement === wrapper.value;
}

onMounted(() => document.addEventListener('fullscreenchange', onFullscreenChange));
onBeforeUnmount(() => document.removeEventListener('fullscreenchange', onFullscreenChange));
</script>

<template>
  <div v-if="display" class="space-y-2">
    <div class="flex gap-2">
      <NInput
        v-model:value="password"
        type="password"
        placeholder="VNC 密码（VNC_PASSWORD，可留空）"
        class="max-w-64"
        size="small"
        aria-label="VNC 密码"
        @keyup.enter="reloadKey++"
      />
      <NButton size="small" @click="reloadKey++">
        <template #icon><Icon icon="lucide:refresh-cw" /></template>
        重连
      </NButton>
      <NButton size="small" :aria-label="isFullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
        <template #icon>
          <Icon :icon="isFullscreen ? 'lucide:minimize' : 'lucide:maximize'" />
        </template>
        {{ isFullscreen ? '退出全屏' : '全屏' }}
      </NButton>
    </div>
    <div ref="wrapper" class="vnc-wrapper" :class="{ 'vnc-fullscreen': isFullscreen }">
      <iframe
        :key="reloadKey"
        :src="src"
        class="h-[60vh] w-full rounded-md border border-border bg-card"
        :class="{ 'vnc-iframe-fullscreen': isFullscreen }"
        title="noVNC 浏览器视图"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  </div>
  <p v-else class="py-8 text-center text-sm text-muted-foreground">
    该会话实例未分配 VNC 显示（本地无头模式）
  </p>
</template>

<style scoped>
.vnc-fullscreen {
  background: hsl(var(--background));
  display: flex;
}

.vnc-iframe-fullscreen {
  height: 100% !important;
  border: none;
  border-radius: 0;
}
</style>
