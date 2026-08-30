<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NSpin, NTabPane, NTabs, useDialog, useMessage } from 'naive-ui';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import CookieTable from '@/components/sessions/CookieTable.vue';
import InteractPanel from '@/components/sessions/InteractPanel.vue';
import NavigateBar from '@/components/sessions/NavigateBar.vue';
import NetworkPanel from '@/components/sessions/NetworkPanel.vue';
import ProxyDialog from '@/components/sessions/ProxyDialog.vue';
import ScreenshotPanel from '@/components/sessions/ScreenshotPanel.vue';
import TabManager from '@/components/sessions/TabManager.vue';
import StatusBadge from '@/components/common/StatusBadge.vue';
import VncFrame from '@/components/instances/VncFrame.vue';
import * as sessionsApi from '@/api/sessions';
import { useInstancesStore } from '@/stores/instances';
import { useSessionsStore } from '@/stores/sessions';

const route = useRoute();
const router = useRouter();
const message = useMessage();
const dialog = useDialog();
const sessionsStore = useSessionsStore();
const instancesStore = useInstancesStore();

const sessionId = computed(() => String(route.params.id));
const session = computed(() => sessionsStore.sessions.find((s) => s.id === sessionId.value));

const viewMode = ref<'screenshot' | 'vnc'>('screenshot');
const showProxy = ref(false);
const html = ref('');
const htmlLoading = ref(false);
const screenshotRef = ref<InstanceType<typeof ScreenshotPanel> | null>(null);
const tabManagerRef = ref<InstanceType<typeof TabManager> | null>(null);
const cookieRef = ref<InstanceType<typeof CookieTable> | null>(null);

// 会话所属实例的 display（从实例池按画像 key 匹配）
const display = computed(() => {
  const key = session.value?.fp_profile_id ?? 'default';
  const inst = instancesStore.instances.find((i) => i.key === key);
  return inst?.display ?? null;
});

onMounted(async () => {
  if (!sessionsStore.sessions.length) await sessionsStore.fetchAll();
  if (!instancesStore.instances.length) void instancesStore.fetchAll();
  if (!session.value) {
    message.error('会话不存在或已被回收');
    void router.replace({ name: 'sessions' });
  }
});

function onNavigated(): void {
  void sessionsStore.fetchAll();
  void tabManagerRef.value?.refresh();
  void cookieRef.value?.refresh();
  screenshotRef.value?.capture();
}

async function loadHtml(): Promise<void> {
  htmlLoading.value = true;
  try {
    html.value = await sessionsApi.getHtml(sessionId.value);
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    htmlLoading.value = false;
  }
}

async function copyHtml(): Promise<void> {
  await navigator.clipboard.writeText(html.value);
  message.success('已复制 HTML');
}

function confirmDelete(): void {
  dialog.warning({
    title: '删除会话',
    content: `确定删除会话 ${sessionId.value}？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await sessionsStore.remove(sessionId.value);
      message.success('会话已删除');
      void router.replace({ name: 'sessions' });
    },
  });
}
</script>

<template>
  <NSpin :show="sessionsStore.loading && !session">
    <div v-if="session" class="space-y-4">
      <!-- 会话信息条 -->
      <NCard size="small">
        <div class="flex flex-wrap items-center gap-2">
          <NButton quaternary size="small" aria-label="返回列表" @click="router.push({ name: 'sessions' })">
            <Icon icon="lucide:arrow-left" class="text-lg" />
          </NButton>
          <span class="font-mono text-lg font-semibold">{{ session.id }}</span>
          <StatusBadge v-if="session.fp_profile_id" status="info" :text="`画像: ${session.fp_profile_id}`" />
          <StatusBadge status="default" :text="`指纹: ${session.fingerprint}`" />
          <div class="flex-1" />
          <NButton size="small" secondary @click="showProxy = true">
            <template #icon><Icon icon="lucide:network" /></template>
            切换代理
          </NButton>
          <NButton size="small" type="error" secondary @click="confirmDelete">
            <template #icon><Icon icon="lucide:trash-2" /></template>
            删除
          </NButton>
        </div>
      </NCard>

      <!-- 导航条 -->
      <NCard size="small">
        <NavigateBar :session-id="sessionId" @navigated="onNavigated" />
      </NCard>

      <!-- 主工作区 -->
      <div class="ncm-detail-grid grid grid-cols-1 gap-4 lg:grid-cols-2">
        <NCard size="small">
          <template #header>
            <div class="flex items-center gap-2">
              <NButton
                size="tiny"
                :type="viewMode === 'screenshot' ? 'primary' : 'default'"
                @click="viewMode = 'screenshot'"
              >
                截图
              </NButton>
              <NButton
                size="tiny"
                :type="viewMode === 'vnc' ? 'primary' : 'default'"
                :disabled="!display"
                @click="viewMode = 'vnc'"
              >
                VNC 实时
              </NButton>
            </div>
          </template>
          <ScreenshotPanel v-if="viewMode === 'screenshot'" ref="screenshotRef" :session-id="sessionId" />
          <VncFrame v-else :display="display" />
        </NCard>

        <NCard size="small" content-class="!pt-0">
          <NTabs type="line" animated>
            <NTabPane name="tabs" tab="标签页">
              <TabManager ref="tabManagerRef" :session-id="sessionId" @changed="screenshotRef?.capture()" />
            </NTabPane>
            <NTabPane name="cookies" tab="Cookie">
              <CookieTable ref="cookieRef" :session-id="sessionId" />
            </NTabPane>
            <NTabPane name="interact" tab="交互">
              <InteractPanel :session-id="sessionId" />
            </NTabPane>
            <NTabPane name="network" tab="网络">
              <NetworkPanel :session-id="sessionId" />
            </NTabPane>
            <NTabPane name="html" tab="HTML">
              <div class="space-y-2">
                <div class="flex gap-2">
                  <NButton size="small" :loading="htmlLoading" @click="loadHtml">
                    <template #icon><Icon icon="lucide:code" /></template>
                    获取当前页 HTML
                  </NButton>
                  <NButton v-if="html" size="small" quaternary @click="copyHtml">
                    <template #icon><Icon icon="lucide:copy" /></template>
                    复制
                  </NButton>
                </div>
                <pre
                  v-if="html"
                  class="max-h-96 overflow-auto rounded-md border border-border bg-accent p-3 text-xs"
                ><code>{{ html }}</code></pre>
              </div>
            </NTabPane>
          </NTabs>
        </NCard>
      </div>

      <ProxyDialog v-model:show="showProxy" :session-id="sessionId" />
    </div>
  </NSpin>
</template>
