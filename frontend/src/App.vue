<script setup lang="ts">
import {
  darkTheme,
  NConfigProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NMessageProvider,
  zhCN,
  dateZhCN,
} from 'naive-ui';
import { computed } from 'vue';

import { useAppStore } from '@/stores/app';

const appStore = useAppStore();
const theme = computed(() => (appStore.isDark ? darkTheme : null));

// naive-ui 主题 token 与 styles/theme.css 的 CSS 变量保持一致（naive 需静态色值做颜色合成，
// 且 seemly 不支持 CSS Color 4 空格语法，必须用逗号分隔的 hsl）。
const lightOverrides = {
  common: {
    primaryColor: 'hsl(217, 91%, 50%)',
    primaryColorHover: 'hsl(217, 91%, 58%)',
    primaryColorPressed: 'hsl(217, 91%, 42%)',
    successColor: 'hsl(142, 71%, 40%)',
    warningColor: 'hsl(32, 95%, 44%)',
    errorColor: 'hsl(0, 72%, 51%)',
    borderRadius: '6px',
  },
};

const darkOverrides = {
  common: {
    ...lightOverrides.common,
    primaryColor: 'hsl(217, 91%, 60%)',
    successColor: 'hsl(142, 69%, 50%)',
    warningColor: 'hsl(38, 92%, 55%)',
    errorColor: 'hsl(0, 72%, 60%)',
  },
};

const themeOverrides = computed(() => (appStore.isDark ? darkOverrides : lightOverrides));
</script>

<template>
  <NConfigProvider :theme="theme" :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <NLoadingBarProvider>
      <NDialogProvider>
        <NMessageProvider>
          <RouterView />
        </NMessageProvider>
      </NDialogProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>
