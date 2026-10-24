<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { number } from '~/utils/presentation'

// How remaining demand moved, what was already bought (kept) and the gap this round covers.
defineProps<{ before: number; after: number; reason?: string; keep?: number; gap?: number }>()
</script>
<template>
  <div class="surface-demand" role="group" :aria-label="tr('需求变化')">
    <p v-if="reason" class="surface-demand-reason">{{ reason }}</p>
    <dl class="space-change-grid">
      <div>
        <dt>{{ tr('剩余需求') }}</dt>
        <dd>{{ joinText([number(before), '→', number(after), tr('件')], ' ') }}</dd>
      </div>
      <div v-if="keep !== undefined">
        <dt>{{ tr('已执行采购') }}</dt>
        <dd>{{ tr('{0} 件 · 保留', [number(keep)]) }}</dd>
      </div>
      <div v-if="gap !== undefined">
        <dt>{{ tr('这次只补缺口') }}</dt>
        <dd>{{ tr('{0} 件', [number(gap)]) }}</dd>
      </div>
    </dl>
  </div>
</template>
