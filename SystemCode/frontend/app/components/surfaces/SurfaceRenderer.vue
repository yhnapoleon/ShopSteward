<script setup lang="ts">
import type { NextStepTarget, Surface } from '~/surfaces/types'
import { contentKey } from '~/surfaces/derive'
import ClarificationForm from './ClarificationForm.vue'
import DemandChange from './DemandChange.vue'
import EvidenceList from './EvidenceList.vue'
import MetricRow from './MetricRow.vue'
import NextStep from './NextStep.vue'
import PlanComparison from './PlanComparison.vue'
import QuoteTable from './QuoteTable.vue'
import TextBlock from './TextBlock.vue'

// Renders a surface block by block (redesign §9). When a surface's content first appears its
// blocks fade in 50 ms apart; the elements are keyed by that content, so a background refresh
// with the same content keeps them and nothing replays. `identity` lets a caller key by its
// source (a result, an outcome) so that switching language does not count as new content.
// Blocks only report intent upwards: open an existing dialog or view, or send an answer as a
// message. NextStep and ClarificationForm appear only where the caller handles those events.
// A surface placed inside a closed fold passes `animate: false`; opening a fold is not an entrance.
const props = withDefaults(
  defineProps<{ surface: Surface; identity?: string; interactive?: boolean; animate?: boolean }>(),
  { identity: undefined, interactive: false, animate: true },
)
const emit = defineEmits<{ open: [name: NextStepTarget]; submit: [text: string] }>()
const key = computed(() => props.identity ?? contentKey(props.surface))
// The entrance class stays only while the entrance can play; a block revealed later appears
// without motion.
const entering = ref(props.animate)
let timer: ReturnType<typeof setTimeout> | undefined
watch(
  key,
  () => {
    clearTimeout(timer)
    entering.value = props.animate
    if (props.animate) timer = setTimeout(() => (entering.value = false), 640)
  },
  { immediate: true },
)
onUnmounted(() => clearTimeout(timer))
const step = (index: number) => ({ '--surface-i': String(Math.min(index, 5)) })
</script>
<template>
  <div :key="key" class="surface" :class="{ 'is-entering': entering }">
    <template v-for="(block, index) in surface.blocks" :key="index">
      <MetricRow
        v-if="block.component === 'MetricRow'"
        v-bind="block.props"
        class="surface-block"
        :style="step(index)"
      />
      <PlanComparison
        v-else-if="block.component === 'PlanComparison'"
        v-bind="block.props"
        class="surface-block"
        :style="step(index)"
      />
      <EvidenceList
        v-else-if="block.component === 'EvidenceList'"
        v-bind="block.props"
        class="surface-block"
        :style="step(index)"
      />
      <DemandChange
        v-else-if="block.component === 'DemandChange'"
        v-bind="block.props"
        class="surface-block"
        :style="step(index)"
      />
      <QuoteTable
        v-else-if="block.component === 'QuoteTable'"
        v-bind="block.props"
        class="surface-block"
        :style="step(index)"
      />
      <NextStep
        v-else-if="block.component === 'NextStep' && interactive"
        v-bind="block.props"
        class="surface-block"
        :style="step(index)"
        @open="emit('open', $event)"
      />
      <ClarificationForm
        v-else-if="block.component === 'ClarificationForm' && interactive"
        v-bind="block.props"
        class="surface-block"
        :style="step(index)"
        @submit="emit('submit', $event)"
      />
      <TextBlock
        v-else-if="block.component === 'Text'"
        v-bind="block.props"
        class="surface-block"
        :style="step(index)"
      />
    </template>
  </div>
</template>
