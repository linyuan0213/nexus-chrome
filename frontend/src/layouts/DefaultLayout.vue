<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NDrawer, NDrawerContent, NMenu, NTooltip } from 'naive-ui';
import type { MenuOption } from 'naive-ui';
import { computed, h, onMounted, ref } from 'vue';
import { RouterView, useRoute, useRouter } from 'vue-router';

import { usePolling } from '@/composables/usePolling';
import { useEventStream } from '@/composables/useEventStream';
import * as authApi from '@/api/auth';
import { useAppStore } from '@/stores/app';
import { useEventsStore } from '@/stores/events';

const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const eventsStore = useEventsStore();

useEventStream();
usePolling(
  () => appStore.refreshStatus(),
  () => appStore.pollInterval,
);
onMounted(() => {
  void appStore.refreshStatus();
});

const drawerVisible = ref(false);

function renderIcon(name: string) {
  return () => h(Icon, { icon: name });
}

const menuOptions: MenuOption[] = [
  { label: '概览', key: 'dashboard', icon: renderIcon('lucide:layout-dashboard') },
  { label: '会话', key: 'sessions', icon: renderIcon('lucide:app-window') },
  { label: '指纹画像', key: 'profiles', icon: renderIcon('lucide:fingerprint') },
  { label: '实例', key: 'instances', icon: renderIcon('lucide:server') },
  { label: '事件', key: 'events', icon: renderIcon('lucide:activity') },
  { label: '调试台', key: 'playground', icon: renderIcon('lucide:terminal') },
  { label: 'API Keys', key: 'api-keys', icon: renderIcon('lucide:key-round') },
  { label: '设置', key: 'settings', icon: renderIcon('lucide:settings') },
];

const activeKey = computed(() => {
  const name = route.name;
  if (name === 'session-detail') return 'sessions';
  if (name === 'profile-detail') return 'profiles';
  return String(name ?? 'dashboard');
});

function onMenuSelect(key: string): void {
  drawerVisible.value = false;
  void router.push({ name: key });
}

const serverBadge = computed(() => {
  if (appStore.statusError) return { text: '服务离线', cls: 'text-destructive' };
  if (!appStore.status) return { text: '连接中…', cls: 'text-muted-foreground' };
  return { text: `v${appStore.status.version}`, cls: 'text-success' };
});

function toggleTheme(): void {
  appStore.setTheme(appStore.isDark ? 'light' : 'dark');
}

/** 登出：通知后端吊销 session token，清空本地凭证并回登录页。 */
async function logout(): Promise<void> {
  try {
    await authApi.logout();
  } catch {
    // 忽略网络错误，本地照常清理
  }
  appStore.saveToken('');
  void router.push({ name: 'login' });
}
</script>

<template>
  <div class="flex h-dvh">
    <!-- 桌面侧边栏 -->
    <aside
      class="hidden w-56 shrink-0 flex-col bg-sidebar text-sidebar-foreground md:flex"
      aria-label="主导航"
    >
      <div class="flex h-14 items-center gap-2 px-4 font-semibold">
        <Icon icon="lucide:chrome" class="text-xl text-sidebar-active" aria-hidden="true" />
        <span>Nexus Chrome</span>
      </div>
      <NMenu
        :value="activeKey"
        :options="menuOptions"
        :indent="18"
        class="ncm-menu flex-1"
        @update:value="onMenuSelect"
      />
    </aside>

    <!-- 移动端抽屉 -->
    <NDrawer v-model:show="drawerVisible" placement="left" :width="224">
      <NDrawerContent closable>
        <template #header>Nexus Chrome</template>
        <NMenu :value="activeKey" :options="menuOptions" @update:value="onMenuSelect" />
      </NDrawerContent>
    </NDrawer>

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- 顶栏 -->
      <header class="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
        <div class="md:hidden">
          <NButton quaternary aria-label="打开菜单" @click="drawerVisible = true">
            <Icon icon="lucide:menu" class="text-xl" />
          </NButton>
        </div>

        <h1 class="truncate text-base font-medium">{{ route.meta?.title ?? '' }}</h1>
        <div class="flex-1" />

        <NTooltip>
          <template #trigger>
            <span class="flex items-center gap-1.5 text-sm" :class="serverBadge.cls">
              <Icon icon="lucide:heart-pulse" aria-hidden="true" />
              {{ serverBadge.text }}
            </span>
          </template>
          {{ appStore.statusError || '服务正常' }}
        </NTooltip>

        <NTooltip>
          <template #trigger>
            <span
              class="flex items-center"
              :class="eventsStore.connected ? 'text-success' : 'text-destructive'"
              role="status"
              :aria-label="eventsStore.connected ? '事件流已连接' : '事件流断开'"
            >
              <Icon icon="lucide:radio" class="text-lg" />
            </span>
          </template>
          事件流：{{ eventsStore.connected ? '已连接' : '已断开' }}
        </NTooltip>

        <NButton quaternary aria-label="切换主题" @click="toggleTheme">
          <Icon :icon="appStore.isDark ? 'lucide:sun' : 'lucide:moon'" class="text-lg" />
        </NButton>
        <NButton v-if="appStore.authEnabled" quaternary aria-label="登出" @click="logout">
          <Icon icon="lucide:log-out" class="text-lg" />
        </NButton>
      </header>

      <!-- 内容区 -->
      <main class="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.ncm-menu {
  --n-item-text-color: hsl(var(--sidebar-foreground)) !important;
  --n-item-icon-color: hsl(var(--sidebar-foreground)) !important;
  --n-item-text-color-hover: hsl(var(--primary-foreground)) !important;
  --n-item-icon-color-hover: hsl(var(--primary-foreground)) !important;
  --n-item-text-color-active: hsl(var(--primary-foreground)) !important;
  --n-item-icon-color-active: hsl(var(--primary-foreground)) !important;
  --n-item-color-active: hsl(var(--sidebar-active)) !important;
  --n-item-color-hover: hsl(var(--accent) / 0.3) !important;
}
</style>
