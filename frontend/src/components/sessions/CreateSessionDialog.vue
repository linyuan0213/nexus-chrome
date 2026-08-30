<script setup lang="ts">
import { NButton, NForm, NFormItem, NInput, NModal, NSelect, useMessage } from 'naive-ui';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useProfilesStore } from '@/stores/profiles';
import { useSessionsStore } from '@/stores/sessions';

const show = defineModel<boolean>('show', { required: true });
const emit = defineEmits<{ created: [id: string] }>();

const router = useRouter();
const message = useMessage();
const sessionsStore = useSessionsStore();
const profilesStore = useProfilesStore();

const form = ref({
  session_id: '',
  fingerprint_profile: 'stealth',
  fp_profile_id: null as string | null,
  user_agent: '',
  proxy: '',
});
const submitting = ref(false);

const fingerprintOptions = [
  { label: 'default', value: 'default' },
  { label: 'stealth', value: 'stealth' },
  { label: 'paranoid', value: 'paranoid' },
];

onMounted(() => {
  if (!profilesStore.profiles.length) void profilesStore.fetchAll();
});

async function submit(): Promise<void> {
  if (!form.value.session_id.trim()) {
    message.warning('请填写会话 ID');
    return;
  }
  submitting.value = true;
  try {
    await sessionsStore.create({
      session_id: form.value.session_id.trim(),
      fingerprint_profile: form.value.fingerprint_profile,
      fp_profile_id: form.value.fp_profile_id || null,
      user_agent: form.value.user_agent || null,
      proxy: form.value.proxy || null,
    });
    message.success(`会话 ${form.value.session_id} 已创建`);
    show.value = false;
    const id = form.value.session_id.trim();
    form.value.session_id = '';
    emit('created', id);
    void router.push({ name: 'session-detail', params: { id } });
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <NModal :show="show" preset="card" title="新建会话" class="w-[95vw] max-w-lg" @update:show="show = $event">
    <NForm label-placement="top">
      <NFormItem label="会话 ID" required>
        <NInput v-model:value="form.session_id" placeholder="如 work、site-a" />
      </NFormItem>
      <NFormItem label="指纹画像（配置中心）">
        <NSelect
          v-model:value="form.fp_profile_id"
          :options="
            profilesStore.profiles.map((p) => ({
              label: `${p.name || p.profile_id} (v${p.version})`,
              value: p.profile_id,
            }))
          "
          clearable
          placeholder="不绑定（使用预置指纹）"
        />
      </NFormItem>
      <NFormItem v-if="!form.fp_profile_id" label="预置指纹配置">
        <NSelect v-model:value="form.fingerprint_profile" :options="fingerprintOptions" />
      </NFormItem>
      <NFormItem label="自定义 User-Agent（可选）">
        <NInput v-model:value="form.user_agent" placeholder="留空使用画像/默认值" />
      </NFormItem>
      <NFormItem label="代理（可选）">
        <NInput v-model:value="form.proxy" placeholder="http://user:pass@host:port" />
      </NFormItem>
    </NForm>
    <template #footer>
      <div class="flex justify-end gap-2">
        <NButton @click="show = false">取消</NButton>
        <NButton type="primary" :loading="submitting" @click="submit">创建</NButton>
      </div>
    </template>
  </NModal>
</template>
