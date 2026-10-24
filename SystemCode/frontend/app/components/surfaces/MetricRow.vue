<script setup lang="ts">
import type { MetricItem } from '~/surfaces/types'

// Key figures side by side. Values arrive formatted; a unit follows its number after a space.
const props = defineProps<{ label?: string; items: MetricItem[] }>()
const columns = computed(() => String(props.items.length <= 4 ? props.items.length : 3))
</script>
<template>
  <div
    class="surface-metrics"
    :role="label ? 'group' : undefined"
    :aria-label="label"
    :style="{ '--metric-cols': columns }"
  >
    <div v-for="(item, index) in items" :key="index" class="surface-metric">
      <small>{{ item.label }}</small
      ><strong
        >{{ item.value
        }}<span v-if="item.unit" class="surface-unit">{{ ' ' + item.unit }}</span></strong
      ><span v-if="item.hint" class="surface-metric-hint">{{ item.hint }}</span>
    </div>
  </div>
</template>
