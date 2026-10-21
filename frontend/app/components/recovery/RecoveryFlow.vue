<script setup lang="ts">
import { t as tr } from '~/i18n'
import { useReducedMotion } from 'motion-v'
import { flowSteps } from '~/utils/recovery'
import { recoveryFlowKey, useRecoveryFlow } from '~/composables/useRecoveryFlow'

// Emergency restock on the work page (workspace §18): one card at the top of the left column
// while a restock is under way, one progress line, and the next step always at the card's
// bottom right. When it is over the card shrinks to a one-line result.
const props = defineProps<{ missionId: string }>()
const emit = defineEmits<{ confirm: [] }>()
const flow = useRecoveryFlow(() => props.missionId)
provide(recoveryFlowKey, flow)
flow.onConfirm(() => emit('confirm'))
const reduce = useReducedMotion()
const state = computed(() => flow.flow.value)
/** A slow call of ours is the system working too; an unconfirmed submission waits on the owner. */
const actor = computed(() => flow.actor.value)
const stage = computed(() =>
  state.value.stage === 'confirm' && flow.revisiting.value ? 'compare' : state.value.stage,
)
const steps = computed(() => flowSteps(state.value.variant, flow.hasOriginals.value))
const current = computed(() =>
  Math.max(
    0,
    steps.value.findIndex((s) => s.key === state.value.stage),
  ),
)
// A creation whose answer was lost shows too, even with no Case read yet: it waits to be verified.
const visible = computed(() => !!flow.brief.value || !!flow.detail.value || flow.unconfirmed.value)
const expanded = ref(false)
watch(
  () => flow.detail.value?.id,
  () => (expanded.value = false),
)
const summary = computed(() => state.value.ended && !expanded.value && !flow.brief.value)
const root = ref<HTMLElement | null>(null)
const reveal = async (block: ScrollLogicalPosition) => {
  await nextTick()
  root.value?.scrollIntoView({ behavior: reduce.value ? 'auto' : 'smooth', block })
}
watch(
  () => flow.focus.value,
  () => reveal('start'),
)
/** The stage that leaves goes at once (removed now, never kept beside the next one). */
const leaveNow = (_el: Element, done: () => void) => done()
// A stage that changes while the page is open swaps in place; loading the page does not animate:
// the swap is armed only once the first complete state (the Case and its purchases) is shown.
const live = ref(false)
watch(
  () => flow.loaded.value,
  async (loaded) => {
    if (!loaded || live.value) return
    await nextTick()
    requestAnimationFrame(() => (live.value = true))
  },
  { immediate: true },
)
// The card folds to its result line (or opens again) while the page is open: the new content
// fades in, and a result line left above the screen is brought back into view.
const moved = ref(false)
watch(summary, (value) => {
  moved.value = live.value
  if (value && live.value) void reveal('nearest')
})
</script>
<template>
  <section
    v-if="visible"
    ref="root"
    class="rf glass"
    :class="{ 'is-summary': summary, 'is-moved': moved }"
    :aria-label="tr('应急补货')"
    data-recovery-flow
    :data-stage="summary ? 'summary' : stage"
    :data-actor="actor"
  >
    <RecoveryOutcome v-if="summary" compact @expand="expanded = true" />
    <template v-else>
      <header class="rf-head">
        <span class="rf-eyebrow"><AppIcon name="truck" />{{ tr('应急补货') }}</span
        ><button
          v-if="state.ended && !flow.brief.value"
          class="text-link"
          @click="expanded = false"
        >
          {{ tr('收起') }}<AppIcon name="chevron-down" />
        </button>
      </header>
      <SpaceFlowProgress
        :steps="steps"
        :current="current"
        :actor="actor"
        :label="tr('应急补货进度')"
      />
      <!-- No out-in: the stage that leaves goes at once, the next one enters in its place. -->
      <Transition :name="live ? 'rf-swap' : 'rf-still'" @leave="leaveNow">
        <RecoveryUnconfirmed v-if="flow.unconfirmed.value" key="unconfirmed" />
        <RecoveryBrief v-else-if="stage === 'brief'" key="brief" />
        <RecoveryCompare v-else-if="stage === 'compare'" key="compare" />
        <RecoveryConfirm v-else-if="stage === 'confirm'" key="confirm" />
        <RecoveryOrder v-else-if="stage === 'order'" key="order" />
        <RecoveryReceive v-else-if="stage === 'receive'" key="receive" />
        <RecoveryOutcome v-else key="result" />
      </Transition>
    </template>
  </section>
</template>
