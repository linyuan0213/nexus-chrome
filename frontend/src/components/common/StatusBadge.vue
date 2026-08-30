<script setup lang="ts">
import { NTag } from 'naive-ui';
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    status: 'success' | 'warning' | 'error' | 'info' | 'default';
    text: string;
  }>(),
  {},
);

const tagType = computed(() => {
  switch (props.status) {
    case 'success':
      return 'success';
    case 'warning':
      return 'warning';
    case 'error':
      return 'error';
    case 'info':
      return 'info';
    default:
      return 'default';
  }
});
</script>

<template>
  <NTag :type="tagType" size="small" :bordered="false">{{ text }}</NTag>
</template>
