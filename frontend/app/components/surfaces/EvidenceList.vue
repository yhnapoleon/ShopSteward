<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { EvidenceItem } from '~/surfaces/types'

// Assumptions, sources and limits. Folded by default: identifiers are for tracing, not reading.
defineProps<{ label?: string; items: EvidenceItem[] }>()
</script>
<template>
  <details class="surface-evidence">
    <summary>{{ label || tr('依据与假设') }}</summary>
    <ul>
      <li v-for="(item, index) in items" :key="index">
        {{ item.label
        }}<small v-if="item.type || item.id">{{
          joinText(item.type && item.id ? ['·', item.type, '/', item.id] : ['·', item.type || item.id])
        }}</small>
      </li>
    </ul>
  </details>
</template>
