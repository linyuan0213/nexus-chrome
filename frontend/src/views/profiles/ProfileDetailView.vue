<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NCard, NInput, NSpin, NSwitch, useMessage } from 'naive-ui';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import FingerprintFieldsEditor from '@/components/profiles/FingerprintFieldsEditor.vue';
import GrayPublishDialog from '@/components/profiles/GrayPublishDialog.vue';
import VersionTimeline from '@/components/profiles/VersionTimeline.vue';
import { emptyProfile, formToProfile, profileToForm } from '@/components/profiles/fingerprint-schema';
import type { ProfileFormModel } from '@/components/profiles/fingerprint-schema';
import * as api from '@/api/profiles';
import type { FpProfile, RolloutRule } from '@/api/types';
import { useProfilesStore } from '@/stores/profiles';

const route = useRoute();
const router = useRouter();
const message = useMessage();
const profilesStore = useProfilesStore();

const profileId = computed(() => String(route.params.id));
const isNew = computed(() => profileId.value === '_new');

const form = ref<ProfileFormModel | null>(null);
const rollout = ref<RolloutRule>({ percent: 100, nodes: [] });
const currentVersion = ref(1);
const loading = ref(false);
const saving = ref(false);
const showVersions = ref(false);
const showGray = ref(false);

onMounted(async () => {
  if (isNew.value) {
    form.value = profileToForm(emptyProfile());
    form.value.profile_id = '';
    return;
  }
  loading.value = true;
  try {
    if (!profilesStore.profiles.length) await profilesStore.fetchAll();
    const summary = profilesStore.profiles.find((p) => p.profile_id === profileId.value);
    if (!summary) throw new Error('画像不存在');
    // 列表接口不含指纹字段，需经节点拉取接口获取完整画像
    const full = await api.getProfile(profileId.value);
    const profile: FpProfile = {
      profile_id: summary.profile_id,
      name: summary.name ?? '',
      version: full.version ?? summary.version,
      enabled: summary.enabled ?? true,
      rollout: summary.rollout ?? { percent: 100, nodes: [] },
      fingerprint: { ...emptyProfile().fingerprint, ...full.data },
    };
    currentVersion.value = profile.version;
    rollout.value = profile.rollout;
    form.value = profileToForm(profile);
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
    void router.replace({ name: 'profiles' });
  } finally {
    loading.value = false;
  }
});

async function save(): Promise<void> {
  if (!form.value) return;
  if (!form.value.profile_id.trim()) {
    message.warning('请填写画像 ID');
    return;
  }
  // 提前校验 JSON 字段
  try {
    const payload = formToProfile(form.value, rollout.value, currentVersion.value);
    saving.value = true;
    await api.saveProfile(payload);
    message.success('画像已保存（版本 +1）');
    await profilesStore.fetchAll();
    if (isNew.value) {
      void router.replace({ name: 'profile-detail', params: { id: payload.profile_id } });
    }
    currentVersion.value += 1;
  } catch (e) {
    message.error(
      e instanceof SyntaxError
        ? `WebGL 参数 JSON 格式错误: ${e.message}`
        : e instanceof Error
          ? e.message
          : String(e),
    );
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <NSpin :show="loading">
    <div v-if="form" class="mx-auto max-w-4xl space-y-4">
      <NCard size="small">
        <div class="flex flex-wrap items-center gap-3">
          <NButton quaternary size="small" aria-label="返回列表" @click="router.push({ name: 'profiles' })">
            <Icon icon="lucide:arrow-left" class="text-lg" />
          </NButton>
          <h2 class="text-lg font-medium">{{ isNew ? '新建画像' : `画像 ${profileId}` }}</h2>
          <span v-if="!isNew" class="text-sm text-muted-foreground">v{{ currentVersion }}</span>
          <div class="flex-1" />
          <NButton v-if="!isNew" size="small" secondary @click="showVersions = true">
            <template #icon><Icon icon="lucide:history" /></template>
            版本历史
          </NButton>
          <NButton v-if="!isNew" size="small" secondary @click="showGray = true">
            <template #icon><Icon icon="lucide:git-branch" /></template>
            灰度发布
          </NButton>
          <NButton type="primary" :loading="saving" @click="save">
            <template #icon><Icon icon="lucide:save" /></template>
            保存
          </NButton>
        </div>
      </NCard>

      <NCard size="small" title="基本信息">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label class="mb-1 block text-xs text-muted-foreground" for="profile-id">画像 ID *</label>
            <NInput
              id="profile-id"
              v-model:value="form.profile_id"
              :disabled="!isNew"
              placeholder="如 mac_work"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs text-muted-foreground" for="profile-name">名称</label>
            <NInput id="profile-name" v-model:value="form.name" placeholder="如 macOS 自洽指纹" />
          </div>
          <div>
            <label class="mb-1 block text-xs text-muted-foreground">启用</label>
            <NSwitch v-model:value="form.enabled" />
          </div>
        </div>
      </NCard>

      <NCard size="small" title="指纹字段">
        <p class="mb-3 text-xs text-muted-foreground">
          留空/为 0 的字段由服务端按平台自动生成自洽值。注意 cores 应与宿主机一致，UA
          版本应与浏览器二进制一致。
        </p>
        <FingerprintFieldsEditor v-model="form" />
      </NCard>

      <VersionTimeline
        v-if="!isNew"
        v-model:show="showVersions"
        :profile-id="profileId"
        @rolled-back="profilesStore.fetchAll()"
      />
      <GrayPublishDialog
        v-if="!isNew"
        v-model:show="showGray"
        :profile-id="profileId"
        :rollout="rollout"
        @published="profilesStore.fetchAll()"
      />
    </div>
  </NSpin>
</template>
