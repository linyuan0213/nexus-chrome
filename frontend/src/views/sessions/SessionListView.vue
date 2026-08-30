<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NInput, useDialog, useMessage } from 'naive-ui';
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import CreateSessionDialog from '@/components/sessions/CreateSessionDialog.vue';
import EmptyState from '@/components/common/EmptyState.vue';
import StatusBadge from '@/components/common/StatusBadge.vue';
import { clearRecoveredSessions } from '@/api/sessions';
import { useSessionsStore } from '@/stores/sessions';

const route = useRoute();
const router = useRouter();
const store = useSessionsStore();
const dialog = useDialog();
const message = useMessage();

const showCreate = ref(false);
const search = ref('');
const clearing = ref(false);

async function clearRecovered(): Promise<void> {
  clearing.value = true;
  try {
    await clearRecoveredSessions();
    message.success('已清除遗留会话记录');
    await store.fetchAll();
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    clearing.value = false;
  }
}

watch(
  () => route.query.create,
  (v) => {
    if (v === '1') showCreate.value = true;
  },
  { immediate: true },
);

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return store.sessions;
  return store.sessions.filter(
    (s) =>
      s.id.toLowerCase().includes(q) ||
      (s.fp_profile_id ?? '').toLowerCase().includes(q) ||
      s.cookie_domains.some((d) => d.toLowerCase().includes(q)),
  );
});

function confirmDelete(id: string): void {
  dialog.warning({
    title: '删除会话',
    content: `确定删除会话 ${id}？会话 Cookie 与标签页将销毁。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await store.remove(id);
        message.success(`会话 ${id} 已删除`);
      } catch (e) {
        message.error(e instanceof Error ? e.message : String(e));
      }
    },
  });
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-2">
      <h2 class="text-lg font-medium">会话</h2>
      <NButton
        size="small"
        quaternary
        aria-label="刷新会话"
        :loading="store.loading"
        @click="store.fetchAll()"
      >
        <Icon icon="lucide:refresh-cw" />
      </NButton>
      <div class="flex-1" />
      <NInput
        v-model:value="search"
        placeholder="搜索会话 / 画像 / 域名"
        clearable
        class="w-56"
        aria-label="搜索会话"
      >
        <template #prefix><Icon icon="lucide:search" /></template>
      </NInput>
      <NButton type="primary" @click="showCreate = true">
        <template #icon><Icon icon="lucide:plus" /></template>
        新建会话
      </NButton>
    </div>

    <NCard v-if="store.recovered.length" size="small" class="border-warning">
      <div class="flex items-center gap-2 text-sm">
        <Icon icon="lucide:history" class="text-warning" />
        <span>检测到 {{ store.recovered.length }} 个上次进程遗留会话，重新创建同名会话即可恢复 Cookie。</span>
        <div class="flex-1" />
        <NButton size="tiny" quaternary :loading="clearing" @click="clearRecovered">
          <template #icon><Icon icon="lucide:trash-2" /></template>
          清除遗留记录
        </NButton>
      </div>
    </NCard>

    <EmptyState
      v-if="!store.loading && filtered.length === 0"
      icon="lucide:app-window"
      title="暂无会话"
      description="创建会话后可自动过盾、提取 Cookie、执行页面交互"
      action-text="新建会话"
      @action="showCreate = true"
    />

    <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <NCard
        v-for="s in filtered"
        :key="s.id"
        size="small"
        hoverable
        class="cursor-pointer"
        @click="router.push({ name: 'session-detail', params: { id: s.id } })"
      >
        <div class="flex items-center justify-between">
          <span class="font-mono font-medium">{{ s.id }}</span>
          <NButton
            size="tiny"
            quaternary
            type="error"
            aria-label="删除会话"
            @click.stop="confirmDelete(s.id)"
          >
            <Icon icon="lucide:trash-2" />
          </NButton>
        </div>
        <div class="mt-2 flex flex-wrap gap-1.5">
          <StatusBadge v-if="s.fp_profile_id" status="info" :text="`画像: ${s.fp_profile_id}`" />
          <StatusBadge status="default" :text="`指纹: ${s.fingerprint}`" />
          <StatusBadge status="default" :text="`${s.tabs.length} 标签页`" />
        </div>
        <div v-if="s.cookie_domains.length" class="mt-2 truncate text-xs text-muted-foreground">
          {{ s.cookie_domains.join('、') }}
        </div>
      </NCard>
    </div>

    <CreateSessionDialog v-model:show="showCreate" />
  </div>
</template>
