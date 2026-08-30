<script setup lang="ts">
import { Icon } from '@iconify/vue';
import { NButton } from 'naive-ui';

defineProps<{
  icon?: string;
  title: string;
  description?: string;
  actionText?: string;
}>();

const emit = defineEmits<{ action: [] }>();
</script>

<template>
  <div role="status" class="flex flex-col items-center py-12 text-center">
    <Icon :icon="icon ?? 'lucide:inbox'" class="text-4xl text-muted-foreground" aria-hidden="true" />
    <h3 class="mt-3 text-sm font-medium">{{ title }}</h3>
    <p v-if="description" class="mt-1 text-sm text-muted-foreground">{{ description }}</p>
    <NButton v-if="actionText" class="mt-4" size="small" @click="emit('action')">
      {{ actionText }}
    </NButton>
  </div>
</template>
