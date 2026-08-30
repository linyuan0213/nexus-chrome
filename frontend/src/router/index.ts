/** 路由表 + 认证守卫。 */

import { createRouter, createWebHistory } from 'vue-router';

import { getToken } from '@/api/client';
import { useAppStore } from '@/stores/app';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/DefaultLayout.vue'),
      children: [
        { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
        {
          path: 'sessions',
          name: 'sessions',
          component: () => import('@/views/sessions/SessionListView.vue'),
        },
        {
          path: 'sessions/:id',
          name: 'session-detail',
          component: () => import('@/views/sessions/SessionDetailView.vue'),
        },
        {
          path: 'profiles',
          name: 'profiles',
          component: () => import('@/views/profiles/ProfileListView.vue'),
        },
        {
          path: 'profiles/:id',
          name: 'profile-detail',
          component: () => import('@/views/profiles/ProfileDetailView.vue'),
        },
        { path: 'instances', name: 'instances', component: () => import('@/views/InstancesView.vue') },
        { path: 'events', name: 'events', component: () => import('@/views/EventsView.vue') },
        { path: 'api-keys', name: 'api-keys', component: () => import('@/views/ApiKeysView.vue') },
        { path: 'playground', name: 'playground', component: () => import('@/views/PlaygroundView.vue') },
        { path: 'settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});

/** 认证守卫：后端开启认证（AUTH_PASSWORD）且无 token 时跳登录页。 */
router.beforeEach(async (to) => {
  if (to.meta.public) return true;
  const appStore = useAppStore();
  // 首次导航探测后端认证配置
  if (appStore.authEnabled === null) {
    await appStore.checkAuthConfig();
  }
  if (appStore.authEnabled && !getToken()) {
    return { name: 'login', query: { redirect: to.fullPath } };
  }
  return true;
});

export default router;
