<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NDataTable, NInput, NPopconfirm, useMessage } from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import { computed, h, onMounted, ref } from 'vue';

import * as api from '@/api/sessions';
import EmptyState from '@/components/common/EmptyState.vue';
import { copyText } from '@/utils/clipboard';

const props = defineProps<{ sessionId: string }>();
const message = useMessage();

interface CookieRow {
  name: string;
  value: string;
  domain: string;
}

const cookies = ref<CookieRow[]>([]);
const domain = ref('');
const loading = ref(false);

function renderActions(row: CookieRow) {
  return h('div', { class: 'flex gap-1' }, [
    h(
      NButton,
      { size: 'tiny', quaternary: true, onClick: () => copyValue(row) },
      { icon: () => h(Icon, { icon: 'lucide:copy' }) },
    ),
    h(
      NPopconfirm,
      { onPositiveClick: () => deleteCookie(row) },
      {
        trigger: () =>
          h(
            NButton,
            { size: 'tiny', quaternary: true, type: 'error' },
            { icon: () => h(Icon, { icon: 'lucide:trash-2' }) },
          ),
        default: () => `删除 ${row.name}？`,
      },
    ),
  ]);
}

const columns: DataTableColumns<CookieRow> = [
  { title: '名称', key: 'name', width: 160, ellipsis: { tooltip: true } },
  {
    title: '值',
    key: 'value',
    ellipsis: { tooltip: true },
    render: (row) => h('span', { class: 'font-mono text-xs' }, row.value),
  },
  { title: '域名', key: 'domain', width: 160, ellipsis: { tooltip: true } },
  { title: '操作', key: 'actions', width: 140, render: renderActions },
];

/** 当前展示的 Cookie 拼接成 Cookie 头（name=value; name2=value2）。 */
const cookieHeader = computed(() => cookies.value.map((c) => `${c.name}=${c.value}`).join('; '));

async function refresh(): Promise<void> {
  loading.value = true;
  try {
    // 后端返回 {domain: {name: value}}（CookieStore.as_full_dict），拍平为行
    const data = await api.getCookies(props.sessionId, domain.value || undefined);
    cookies.value = Object.entries(data ?? {}).flatMap(([d, cookieMap]) =>
      Object.entries(cookieMap ?? {}).map(([name, value]) => ({ domain: d, name, value })),
    );
  } finally {
    loading.value = false;
  }
}

async function copyValue(row: CookieRow): Promise<void> {
  const ok = await copyText(row.value);
  if (ok) message.success(`已复制 ${row.name}`);
  else message.error('复制失败');
}

async function copyHeader(): Promise<void> {
  if (!cookieHeader.value) {
    message.warning('无 Cookie 可复制');
    return;
  }
  const ok = await copyText(cookieHeader.value);
  if (ok) message.success('已复制 Cookie 头');
  else message.error('复制失败');
}

async function deleteCookie(row: CookieRow): Promise<void> {
  try {
    await api.deleteCookie(props.sessionId, row.domain, row.name);
    message.success(`已删除 ${row.name}`);
    await refresh();
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  }
}

onMounted(refresh);
defineExpose({ refresh });
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap gap-2">
      <NInput
        v-model:value="domain"
        placeholder="按域名过滤（可选）"
        class="max-w-64"
        clearable
        aria-label="域名过滤"
        @keyup.enter="refresh"
      />
      <NButton size="small" :loading="loading" @click="refresh">查询</NButton>
      <div class="flex-1" />
      <NButton size="small" secondary :disabled="!cookies.length" @click="copyHeader">
        <template #icon><Icon icon="lucide:clipboard-copy" /></template>
        复制 Cookie 头
      </NButton>
    </div>

    <p v-if="cookies.length" class="text-xs text-muted-foreground">
      共 {{ cookies.length }} 条 · 复制后的 Cookie 头可直接用于调试台的 fetch/request 或带 Cookie 导航
    </p>

    <EmptyState v-if="!loading && !cookies.length" icon="lucide:cookie" title="暂无 Cookie" />
    <NDataTable
      v-else
      :columns="columns"
      :data="cookies"
      :loading="loading"
      size="small"
      :pagination="{ pageSize: 20 }"
    />
  </div>
</template>
