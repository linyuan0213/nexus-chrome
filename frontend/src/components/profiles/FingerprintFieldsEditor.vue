<script setup lang="ts">
import { NCollapse, NCollapseItem, NDynamicTags, NInput, NInputNumber, NSelect, NSwitch } from 'naive-ui';
import { computed } from 'vue';

import type { FieldDef } from './fingerprint-schema';
import { FIELD_DEFS, FIELD_GROUPS } from './fingerprint-schema';
import type { ProfileFormModel } from './fingerprint-schema';

const model = defineModel<ProfileFormModel>({ required: true });

const byGroup = computed(() =>
  FIELD_GROUPS.map((g) => ({ group: g, fields: FIELD_DEFS.filter((f) => f.group === g) })),
);

function fieldValue(def: FieldDef) {
  return model.value[def.key];
}

function setField(def: FieldDef, v: unknown): void {
  model.value = { ...model.value, [def.key]: v as never };
}
</script>

<template>
  <NCollapse :default-expanded-names="['基础']">
    <NCollapseItem v-for="g in byGroup" :key="g.group" :title="g.group" :name="g.group">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div v-for="def in g.fields" :key="def.key">
          <label class="mb-1 block text-xs text-muted-foreground" :for="`fp-${def.key}`">
            {{ def.label }}
          </label>

          <NInput
            v-if="def.type === 'text'"
            :id="`fp-${def.key}`"
            :value="String(fieldValue(def) ?? '')"
            size="small"
            @update:value="(v: string) => setField(def, v)"
          />
          <NInputNumber
            v-else-if="def.type === 'number'"
            :id="`fp-${def.key}`"
            :value="fieldValue(def) === null ? null : Number(fieldValue(def))"
            size="small"
            class="w-full"
            @update:value="(v: number | null) => setField(def, v)"
          />
          <NSwitch
            v-else-if="def.type === 'switch'"
            :value="Boolean(fieldValue(def))"
            size="small"
            @update:value="(v: boolean) => setField(def, v)"
          />
          <NDynamicTags
            v-else-if="def.type === 'tags'"
            :value="fieldValue(def) as string[]"
            size="small"
            @update:value="(v: string[]) => setField(def, v)"
          />
          <NSelect
            v-else-if="def.type === 'select'"
            :value="Number(fieldValue(def))"
            :options="def.options"
            size="small"
            @update:value="(v: number) => setField(def, v)"
          />
          <NInput
            v-else
            :id="`fp-${def.key}`"
            :value="String(fieldValue(def) ?? '')"
            type="textarea"
            :rows="3"
            size="small"
            class="font-mono text-xs"
            placeholder='{"MAX_TEXTURE_SIZE": 16384}'
            @update:value="(v: string) => setField(def, v)"
          />

          <p v-if="def.hint" class="mt-0.5 text-xs text-muted-foreground">{{ def.hint }}</p>
        </div>
      </div>
    </NCollapseItem>
  </NCollapse>
</template>
