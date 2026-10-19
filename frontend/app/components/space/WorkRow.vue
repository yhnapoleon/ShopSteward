<script setup lang="ts">
import { t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { awaitsOwnerArrival, watchSummary, workBadge } from '~/composables/useSpace'
import { workTitle } from '~/utils/workPresentation'

// One line per work item: title, status, what happens next, the latest change, and "open".
// It keeps the work-card identity (class and data-work-id) that lists and tests rely on.
const props = defineProps<{ item: Schema<'WorkView'> }>()
defineEmits<{ open: [] }>()
const { s } = useShop()
const badge = computed(() =>
  workBadge(props.item, Date.now(), awaitsOwnerArrival(props.item.mission_id, s)),
)
const summary = computed(() => watchSummary(props.item, s))
</script>
<template>
  <article class="work-card space-row" :data-work-id="item.id">
    <div class="space-row-copy">
      <div class="space-row-title">
        <span class="space-row-kind">{{ tr(item.mission_id ? '备货委托' : '我的事项') }}</span
        ><b>{{ workTitle(item) }}</b>
      </div>
      <p v-if="summary.timing || summary.change" class="space-row-meta">
        <span v-if="summary.timing">{{ summary.timing }}</span
        ><span v-if="summary.change" class="space-row-change">{{ summary.change }}</span>
      </p>
    </div>
    <span class="tag" :class="badge.tone">{{ badge.label }}</span>
    <button class="secondary space-row-open" @click="$emit('open')">
      {{ tr('打开') }}<AppIcon name="arrow-up-right" />
    </button>
  </article>
</template>
