<script setup lang="ts">
import { NInput } from 'naive-ui';

const model = defineModel<string>({ required: true });

defineProps<{ placeholder?: string; rows?: number }>();
</script>

<template>
  <NInput
    v-model:value="model"
    type="textarea"
    :placeholder="placeholder"
    :rows="rows ?? 6"
    class="font-mono text-xs"
    aria-label="代码编辑器"
  />
</template>
