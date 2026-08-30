<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton, NModal, NSpin, NTimeline, NTimelineItem, useDialog, useMessage } from 'naive-ui';
import { ref, watch } from 'vue';

import * as api from '@/api/profiles';
import type { VersionsData } from '@/api/types';

const props = defineProps<{ profileId: string }>();
const emit = defineEmits<{ rolledBack: [] }>();

const show = defineModel<boolean>('show', { required: true });

const message = useMessage();
const dialog = useDialog();
const data = ref<VersionsData | null>(null);
const loading = ref(false);

async function load(): Promise<void> {
  if (!props.profileId) return;
  loading.value = true;
  try {
    data.value = await api.getVersions(props.profileId);
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    loading.value = false;
  }
}

watch(show, (v) => {
  if (v) void load();
});

function confirmRollback(version: number): void {
  dialog.warning({
    title: '回滚画像',
    content: `确定回滚到 v${version}？将生成新版本并生效。`,
    positiveText: '回滚',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.rollbackProfile(props.profileId, version);
        message.success(`已回滚到 v${version}`);
        show.value = false;
        emit('rolledBack');
      } catch (e) {
        message.error(e instanceof Error ? e.message : String(e));
      }
    },
  });
}
</script>

<template>
  <NModal :show="show" preset="card" title="版本历史" class="w-[95vw] max-w-2xl" @update:show="show = $event">
    <NSpin :show="loading">
      <NTimeline v-if="data">
        <NTimelineItem
          v-for="v in data.versions"
          :key="v.version"
          :type="v.version === data.current_version ? 'success' : 'default'"
          :title="`v${v.version}${v.version === data.current_version ? '（当前）' : ''}`"
          :content="[v.created_at, v.operator].filter(Boolean).join(' · ')"
        >
          <NButton
            v-if="v.version !== data.current_version"
            size="tiny"
            secondary
            @click="confirmRollback(v.version)"
          >
            <template #icon><Icon icon="lucide:undo-2" /></template>
            回滚到此版本
          </NButton>
        </NTimelineItem>
      </NTimeline>
      <p v-else-if="!loading" class="py-4 text-center text-sm text-muted-foreground">暂无版本记录</p>
    </NSpin>
  </NModal>
</template>
