<script setup lang="ts">
import { t as tr } from '~/i18n'

// One progress line for a piece of work that moves through fixed stages (workspace §18). The
// current stage says who it waits on: the owner ("等你"), the system ("系统在做") or someone with
// the approval right ("等审批"). Labels are catalog keys. Reusable by any flow: the emergency
// restock now, the regular restock later.
type Actor = 'you' | 'system' | 'other' | 'done'
const props = defineProps<{
  steps: { key: string; label: string }[]
  current: number
  actor: Actor
  /** Accessible name of the step list. */
  label: string
}>()
const last = computed(() => Math.max(1, props.steps.length - 1))
const ratio = computed(() =>
  Math.min(1, Math.max(0, (props.actor === 'done' ? last.value : props.current) / last.value)),
)
const words: Record<Actor, string> = {
  you: '等你',
  system: '系统在做',
  other: '等审批',
  done: '已完成',
}
const icons: Record<Actor, string> = { you: 'hand', system: 'orbit', other: 'user', done: 'check' }
const actorText = computed(() => tr(words[props.actor]))
const stateOf = (index: number) =>
  props.actor === 'done' || index < props.current
    ? 'done'
    : index === props.current
      ? 'current'
      : 'next'
// The line fills as stages complete while the page is open; the first render does not animate.
const live = ref(false)
onMounted(() => requestAnimationFrame(() => (live.value = true)))
</script>
<template>
  <div
    class="flow-progress"
    :class="{ 'is-live': live }"
    :data-actor="actor"
    :style="{ '--flow-steps': steps.length, '--flow-ratio': ratio }"
  >
    <div class="flow-rail">
      <span class="flow-track" aria-hidden="true"><span class="flow-fill" /></span>
      <ol class="flow-steps" :aria-label="label">
        <li
          v-for="(step, index) in steps"
          :key="step.key"
          class="flow-step"
          :class="'is-' + stateOf(index)"
          :data-step="step.key"
          :aria-current="stateOf(index) === 'current' && actor !== 'done' ? 'step' : undefined"
        >
          <span class="flow-node" aria-hidden="true"
            ><AppIcon v-if="stateOf(index) === 'done'" name="check"
          /></span>
          <span class="flow-label"
            >{{ tr(step.label)
            }}<span class="flow-sr">{{
              stateOf(index) === 'done'
                ? tr('（已完成）')
                : stateOf(index) === 'current'
                  ? tr('（{0}）', [actorText])
                  : ''
            }}</span></span
          >
          <span
            v-if="stateOf(index) === 'current' && actor !== 'done'"
            class="flow-actor"
            :class="actor"
            aria-hidden="true"
            ><AppIcon :name="icons[actor]" />{{ actorText }}</span
          >
        </li>
      </ol>
    </div>
    <p class="flow-compact" aria-hidden="true">
      <span class="flow-compact-count">{{
        tr('第 {0}/{1} 步', [Math.min(current, steps.length - 1) + 1, steps.length])
      }}</span
      ><b>{{ tr(steps[Math.min(current, steps.length - 1)]?.label || '') }}</b
      ><span class="flow-actor" :class="actor"
        ><AppIcon :name="icons[actor]" />{{ actorText }}</span
      >
    </p>
  </div>
</template>
