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
/** Our own calls in flight are the system working too; an unconfirmed submission waits on the owner. */
const actor = computed(() =>
  flow.working.value ? 'system' : flow.unconfirmed.value ? 'you' : state.value.actor,
)
const stage = computed(() =>
  state.value.stage === 'confirm' && flow.revisiting.value ? 'compare' : state.value.stage,
)
const steps = computed(() => flowSteps(state.value.variant, flow.originals.value.length > 0))
const current = computed(() =>
  Math.max(
    0,
    steps.value.findIndex((s) => s.key === state.value.stage),
  ),
)
const visible = computed(() => !!flow.brief.value || !!flow.detail.value)
const expanded = ref(false)
watch(
  () => flow.detail.value?.id,
  () => (expanded.value = false),
)
const summary = computed(() => state.value.ended && !expanded.value && !flow.brief.value)
const root = ref<HTMLElement | null>(null)
watch(
  () => flow.focus.value,
  async () => {
    await nextTick()
    root.value?.scrollIntoView({ behavior: reduce.value ? 'auto' : 'smooth', block: 'start' })
  },
)
// The page's regular plan line offers the same "重新比价" when the adopted plan has lapsed.
defineExpose({
  again: () => {
    flow.focus.value++
    return flow.again()
  },
})
// A stage that changes while the page is open swaps in place; loading the page does not animate.
const live = ref(false)
onMounted(() => requestAnimationFrame(() => (live.value = true)))
</script>
<template>
  <section
    v-if="visible"
    ref="root"
    class="rf glass"
    :class="{ 'is-summary': summary }"
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
      <Transition :name="live ? 'rf-swap' : 'rf-still'" mode="out-in">
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
