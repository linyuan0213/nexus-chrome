<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NInput } from 'naive-ui';
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { login } from '@/api/auth';
import { useAppStore } from '@/stores/app';

const router = useRouter();
const route = useRoute();
const appStore = useAppStore();

const password = ref('');
const loading = ref(false);
const error = ref('');

onMounted(() => {
  // 未开启认证时直接进首页
  if (appStore.authEnabled === false) void router.replace('/');
});

async function submit(): Promise<void> {
  if (!password.value) {
    error.value = '请输入访问密码';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    const res = await login(password.value);
    appStore.saveToken(res.token);
    await appStore.checkAuthConfig(); // 拉取 VNC 等安全配置
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
    await router.replace(redirect);
  } catch (e) {
    error.value = e instanceof Error && 'status' in e && e.status === 401 ? '密码错误' : '登录失败，请重试';
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <div class="login-logo">
          <Icon icon="lucide:chrome" />
        </div>
        <h1 class="login-title">Nexus Chrome</h1>
        <p class="login-subtitle">浏览器自动化管理台</p>
      </div>

      <form class="login-form" @submit.prevent="submit">
        <label class="login-label" for="login-password">访问密码</label>
        <NInput
          id="login-password"
          v-model:value="password"
          type="password"
          show-password-on="click"
          size="large"
          placeholder="输入 AUTH_PASSWORD"
          :status="error ? 'error' : undefined"
          autofocus
          @keyup.enter="submit"
        />
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <NButton type="primary" size="large" block :loading="loading" attr-type="submit" class="login-submit">
          登 录
        </NButton>
      </form>

      <p class="login-hint">密码由服务端 AUTH_PASSWORD 环境变量控制</p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: hsl(var(--background));
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  padding: 2.5rem 2rem 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.login-brand {
  text-align: center;
  margin-bottom: 2rem;
}

.login-logo {
  width: 56px;
  height: 56px;
  margin: 0 auto 1rem;
  border-radius: 14px;
  background: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.login-title {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0;
}

.login-subtitle {
  margin-top: 0.375rem;
  font-size: 0.8125rem;
  color: hsl(var(--muted-foreground));
}

.login-form {
  width: 100%;
}

.login-label {
  display: block;
  font-size: 0.8125rem;
  color: hsl(var(--muted-foreground));
  margin-bottom: 0.375rem;
}

.login-error {
  margin-top: 0.5rem;
  font-size: 0.8125rem;
  color: hsl(var(--destructive));
}

.login-submit {
  margin-top: 1.25rem;
}

.login-hint {
  margin-top: 1.5rem;
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}
</style>
