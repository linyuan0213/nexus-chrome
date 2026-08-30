<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NDataTable, NInput, NModal, useDialog, useMessage } from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import { h, onMounted, ref } from 'vue';

import { createApiKey, listApiKeys, revokeApiKey } from '@/api/auth';
import type { ApiKeyRecord, CreatedApiKey } from '@/api/auth';
import EmptyState from '@/components/common/EmptyState.vue';
import StatusBadge from '@/components/common/StatusBadge.vue';
import { copyText } from '@/utils/clipboard';
import { useAppStore } from '@/stores/app';

const appStore = useAppStore();
const message = useMessage();
const dialog = useDialog();

const keys = ref<ApiKeyRecord[]>([]);
const loading = ref(false);

const showCreate = ref(false);
const createForm = ref({ name: '', scopes: ['*'] });
const creating = ref(false);
const createdKey = ref<CreatedApiKey | null>(null);

const scopeOptions = [
  { label: '全部权限', value: '*', icon: 'lucide:shield-check', desc: '所有接口' },
  { label: '会话', value: 'sessions', icon: 'lucide:app-window', desc: '/sessions' },
  { label: '实例', value: 'instances', icon: 'lucide:server', desc: '/instances' },
  { label: '画像', value: 'profiles', icon: 'lucide:fingerprint', desc: '/api/profiles' },
];

function toggleScope(value: string): void {
  const scopes = createForm.value.scopes;
  // 选「全部」互斥其他选项；选其他项则去掉「全部」
  if (value === '*') {
    createForm.value.scopes = scopes.includes('*') ? [] : ['*'];
    return;
  }
  const withoutAll = scopes.filter((s) => s !== '*');
  createForm.value.scopes = withoutAll.includes(value)
    ? withoutAll.filter((s) => s !== value)
    : [...withoutAll, value];
}

const columns: DataTableColumns<ApiKeyRecord> = [
  { title: '名称', key: 'name', width: 160 },
  { title: '前缀', key: 'prefix', render: (r) => h('code', { class: 'text-xs' }, `${r.prefix}…`) },
  {
    title: '权限',
    key: 'scopes',
    render: (r) => r.scopes.map((s) => h(StatusBadge, { status: 'info', text: s, class: 'mr-1' })),
  },
  { title: '创建时间', key: 'created_at', width: 170 },
  {
    title: '状态',
    key: 'revoked',
    width: 90,
    render: (r) =>
      h(StatusBadge, { status: r.revoked ? 'default' : 'success', text: r.revoked ? '已吊销' : '有效' }),
  },
  {
    title: '操作',
    key: 'actions',
    width: 90,
    render: (row) =>
      h(
        NButton,
        {
          size: 'tiny',
          quaternary: true,
          type: 'error',
          disabled: row.revoked,
          onClick: () => confirmRevoke(row),
        },
        { icon: () => h(Icon, { icon: 'lucide:ban' }) },
      ),
  },
];

async function refresh(): Promise<void> {
  loading.value = true;
  try {
    const data = await listApiKeys();
    keys.value = data.keys ?? [];
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}

async function submitCreate(): Promise<void> {
  if (!createForm.value.name.trim()) {
    message.warning('请输入名称');
    return;
  }
  creating.value = true;
  try {
    createdKey.value = await createApiKey(createForm.value.name.trim(), createForm.value.scopes);
    showCreate.value = false;
    createForm.value = { name: '', scopes: ['*'] };
    await refresh();
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    creating.value = false;
  }
}

function confirmRevoke(row: ApiKeyRecord): void {
  dialog.warning({
    title: '吊销 API Key',
    content: `确定吊销「${row.name}」？使用该 Key 的程序将立即失去访问权限。`,
    positiveText: '吊销',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await revokeApiKey(row.id);
        message.success('已吊销');
        await refresh();
      } catch (e) {
        message.error(e instanceof Error ? e.message : String(e));
      }
    },
  });
}

async function copyKey(key: string): Promise<void> {
  const ok = await copyText(key);
  if (ok) message.success('已复制');
  else message.error('复制失败，请手动复制');
}

onMounted(refresh);
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-2">
      <h2 class="text-lg font-medium">API Keys</h2>
      <NButton size="small" quaternary aria-label="刷新" :loading="loading" @click="refresh">
        <Icon icon="lucide:refresh-cw" />
      </NButton>
      <div class="flex-1" />
      <NButton type="primary" @click="showCreate = true">
        <template #icon><Icon icon="lucide:plus" /></template>
        新建 Key
      </NButton>
    </div>

    <p class="text-sm text-muted-foreground">
      第三方程序使用 API Key 访问接口（请求头 <code>Authorization: Bearer &lt;key&gt;</code>）。 Key
      与用户登录相互独立，可随时吊销。
    </p>

    <NCard v-if="appStore.authEnabled === false" size="small" class="border-warning">
      <div class="flex items-center gap-2 text-sm">
        <Icon icon="lucide:alert-triangle" class="text-warning" />
        <span>
          当前未启用认证（未设置 AUTH_PASSWORD），API 完全开放，Key 不会被校验。 设置 AUTH_PASSWORD
          并重启后，Key 才会生效。
        </span>
      </div>
    </NCard>

    <NCard size="small">
      <EmptyState
        v-if="!loading && !keys.length"
        icon="lucide:key-round"
        title="暂无 API Key"
        description="为第三方程序创建独立的访问凭证"
        action-text="新建 Key"
        @action="showCreate = true"
      />
      <NDataTable v-else :columns="columns" :data="keys" :loading="loading" size="small" />
    </NCard>

    <!-- 创建 -->
    <NModal
      :show="showCreate"
      preset="card"
      title="新建 API Key"
      class="w-[95vw] max-w-md"
      @update:show="showCreate = $event"
    >
      <div class="space-y-3">
        <div>
          <label class="mb-1 block text-sm" for="key-name">名称</label>
          <NInput id="key-name" v-model:value="createForm.name" placeholder="如 ci-bot、监控脚本" />
        </div>
        <div>
          <label class="mb-1.5 block text-sm">权限范围</label>
          <div class="scope-grid" role="group" aria-label="权限范围">
            <button
              v-for="o in scopeOptions"
              :key="o.value"
              type="button"
              class="scope-card"
              :class="{ 'scope-card-active': createForm.scopes.includes(o.value) }"
              @click="toggleScope(o.value)"
            >
              <Icon :icon="o.icon" class="scope-icon" />
              <span class="scope-label">{{ o.label }}</span>
              <span class="scope-desc">{{ o.desc }}</span>
              <Icon v-if="createForm.scopes.includes(o.value)" icon="lucide:check" class="scope-check" />
            </button>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <NButton @click="showCreate = false">取消</NButton>
          <NButton type="primary" :loading="creating" @click="submitCreate">创建</NButton>
        </div>
      </template>
    </NModal>

    <!-- 创建成功：明文只显示一次 -->
    <NModal
      :show="!!createdKey"
      preset="card"
      title="API Key 已创建"
      class="w-[95vw] max-w-lg"
      @update:show="createdKey = null"
    >
      <div v-if="createdKey" class="space-y-3">
        <p class="text-sm text-warning">明文仅此一次显示，请立即复制保存：</p>
        <div class="flex items-center gap-2">
          <code
            class="flex-1 overflow-x-auto rounded-md border border-border bg-accent p-2 font-mono text-xs"
          >
            {{ createdKey.key }}
          </code>
          <NButton size="small" @click="copyKey(createdKey.key)">
            <template #icon><Icon icon="lucide:copy" /></template>
            复制
          </NButton>
        </div>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.scope-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
}

.scope-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
  padding: 0.625rem 0.75rem;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
  color: hsl(var(--card-foreground));
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.15s,
    background-color 0.15s;
}

.scope-card:hover {
  border-color: hsl(var(--primary));
}

.scope-card-active {
  border-color: hsl(var(--primary));
  background: hsl(var(--primary) / 0.06);
}

.scope-icon {
  font-size: 1.125rem;
  color: hsl(var(--muted-foreground));
}

.scope-card-active .scope-icon {
  color: hsl(var(--primary));
}

.scope-label {
  font-size: 0.8125rem;
  font-weight: 500;
}

.scope-desc {
  font-size: 0.6875rem;
  color: hsl(var(--muted-foreground));
}

.scope-check {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  color: hsl(var(--primary));
  font-size: 0.875rem;
}
</style>
