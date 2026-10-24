<script setup lang="ts">
import { t as tr } from '~/i18n'
import type { NextStepAction, NextStepTarget } from '~/surfaces/types'

// Ways onward. Each one only opens an existing dialog or view; none confirms or purchases.
defineProps<{ actions: NextStepAction[] }>()
const emit = defineEmits<{ open: [name: NextStepTarget] }>()
</script>
<template>
  <div class="surface-next" role="group" :aria-label="tr('下一步')">
    <button
      v-for="(action, index) in actions"
      :key="index"
      type="button"
      class="secondary surface-next-action"
      @click="emit('open', action.open)"
    >
      {{ action.label }}<AppIcon name="arrow-right" />
    </button>
  </div>
</template>
