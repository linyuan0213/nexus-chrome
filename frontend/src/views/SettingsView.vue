<script setup lang="ts">
import { NButton, NCard, NForm, NFormItem, NInputNumber, NSelect, useMessage } from 'naive-ui';
import { NInput } from 'naive-ui';
import { ref } from 'vue';

import JsonViewer from '@/components/common/JsonViewer.vue';
import { useAppStore } from '@/stores/app';
import type { ThemeMode } from '@/stores/app';

const appStore = useAppStore();
const message = useMessage();

const tokenInput = ref(appStore.token);
const vncPasswordInput = ref(appStore.vncPassword);
const themeOptions = [
  { label: '跟随系统', value: 'system' },
  { label: '亮色', value: 'light' },
  { label: '暗色', value: 'dark' },
];

function saveToken(): void {
  appStore.saveToken(tokenInput.value);
  message.success(tokenInput.value ? 'Token 已保存' : 'Token 已清除');
}

function saveVncPassword(): void {
  appStore.saveVncPassword(vncPasswordInput.value);
  message.success(vncPasswordInput.value ? 'VNC 密码已保存' : 'VNC 密码已清除');
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-4">
    <NCard title="API Token" size="small">
      <p class="mb-3 text-sm text-muted-foreground">
        对应后端 FP_ADMIN_TOKEN（画像管理接口鉴权）。留空表示无鉴权（本地模式）。 Token 仅保存在浏览器
        localStorage。
      </p>
      <div class="flex gap-2">
        <NInput
          v-model:value="tokenInput"
          type="password"
          show-password-on="click"
          placeholder="Bearer token"
          aria-label="API Token"
        />
        <NButton type="primary" @click="saveToken">保存</NButton>
      </div>
    </NCard>

    <NCard title="VNC 密码" size="small">
      <p class="mb-3 text-sm text-muted-foreground">
        默认自动使用后端下发的 VNC_PASSWORD（同源信任域）。此处仅用于覆盖后端值，留空则跟随后端。
      </p>
      <div class="flex gap-2">
        <NInput
          v-model:value="vncPasswordInput"
          type="password"
          show-password-on="click"
          placeholder="留空则使用后端的 VNC_PASSWORD"
          aria-label="VNC 密码"
        />
        <NButton type="primary" @click="saveVncPassword">保存</NButton>
      </div>
    </NCard>

    <NCard title="外观与行为" size="small">
      <NForm label-placement="left" label-width="auto">
        <NFormItem label="主题">
          <NSelect
            :value="appStore.theme"
            :options="themeOptions"
            class="w-40"
            @update:value="(v: ThemeMode) => appStore.setTheme(v)"
          />
        </NFormItem>
        <NFormItem label="轮询间隔（秒）">
          <NInputNumber
            :value="appStore.pollInterval / 1000"
            :min="2"
            :max="120"
            class="w-40"
            @update:value="(v: number | null) => (appStore.pollInterval = (v ?? 10) * 1000)"
          />
        </NFormItem>
      </NForm>
    </NCard>

    <NCard title="服务状态" size="small">
      <template #header-extra>
        <NButton size="small" quaternary @click="appStore.refreshStatus()">刷新</NButton>
      </template>
      <JsonViewer v-if="appStore.status" :data="appStore.status" />
      <p v-else class="text-sm text-muted-foreground">
        {{ appStore.statusError || '暂无数据' }}
      </p>
    </NCard>
  </div>
</template>
