<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { useReducedMotion } from 'motion-v'
import { money, number } from '~/utils/presentation'

// One workspace for every work item (workspace redesign §4). A restocking mission is a work
// item with a linked mission: its cards appear on the left, the conversations on the right.
const props = defineProps<{ issue: string | null; working: boolean; panel?: string }>()
const emit = defineEmits<{
  open: [name: string]
  confirm: []
  back: []
  navigate: [view: string]
  changed: []
}>()
const shop = useShop()
const { s, stock, canDecide, hasRole } = shop
const work = useWorkItems()
const agent = useAgentConversation()
const space = useSpace()
const { item, linked, mission, ended, openActions, target } = space
const reduce = useReducedMotion()
const mobilePanel = ref(props.panel === 'agent' ? 'agent' : 'result')
watch(
  () => props.panel,
  (value) => (mobilePanel.value = value === 'agent' ? 'agent' : 'result'),
)
const conversation = ref<{ show: (tab: 'agent' | 'work') => void } | null>(null)
const localError = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
// Same linkage as the task workspace: a finished tool lights up the card it read or changed.
async function highlight(name: string, scroll = false) {
  if (scroll) {
    mobilePanel.value = 'result'
    await nextTick()
  }
  const element = document.getElementById('space-' + name)
  if (!element) {
    // No purchase order on the page yet: the receipt dialog is the detailed record.
    if (scroll && name === 'receipt') emit('open', 'receipt')
    return
  }
  clearTimeout(timer)
  target.value = name
  if (scroll)
    element.scrollIntoView({ behavior: reduce.value ? 'auto' : 'smooth', block: 'center' })
  timer = setTimeout(() => (target.value = ''), 1100)
}
watch(
  () => agent.s.activity?.id,
  () => {
    const activity = agent.s.activity
    // Only tools that finished just now; loading or replaying history never lights anything.
    if (activity && Date.now() - activity.at < 1500) void highlight(activity.target)
  },
)
watch(
  () => item.value?.id,
  () => {
    clearTimeout(timer)
    target.value = ''
    localError.value = ''
  },
)
onUnmounted(() => {
  clearTimeout(timer)
  target.value = ''
})
async function attempt(fn: () => Promise<unknown>) {
  localError.value = ''
  try {
    await fn()
  } catch (e) {
    localError.value = (e as Error).message
  }
}
async function workControl(operation: 'cancel' | 'retry') {
  if (await work.control(operation)) emit('changed')
}
/** Answer in the item's own conversation (the clarification card's free-text route). */
async function converse() {
  mobilePanel.value = 'agent'
  conversation.value?.show('work')
  await nextTick()
  document.getElementById('work-message')?.focus()
}
const expired = computed(
  () =>
    !!item.value?.processing_expires_at &&
    Date.parse(item.value.processing_expires_at) <= Date.now(),
)
const openAlerts = computed(() => s.alerts.filter((a) => a.status === 'OPEN').length)
</script>
<template>
  <section
    v-if="item"
    class="space-workspace"
    :class="{ 'task-workspace': !!mission }"
    :data-task-id="item.mission_id || item.id"
    :data-mobile-panel="mobilePanel"
  >
    <SpaceHeader :issue="issue" @back="emit('back')" @open="emit('open', $event)" />
    <div class="task-mobile-tabs" :aria-label="tr('任务内容切换')">
      <button :aria-pressed="mobilePanel === 'result'" @click="mobilePanel = 'result'">
        {{ tr('方案与进展') }}</button
      ><button :aria-pressed="mobilePanel === 'agent'" @click="mobilePanel = 'agent'">
        {{ tr('Agent 工作') }}<span v-if="agent.active.value" class="agent-live-dot" />
      </button>
    </div>
    <div class="task-columns">
      <div class="task-result-column">
        <template v-if="linked">
          <div class="task-fact-summary" :aria-label="tr('当前经营事实摘要')">
            <span
              >{{ tr(s.connected ? '可用现金' : '上次现金')
              }}<b>{{ tr(money(s.dashboard?.state.available_cash_minor)) }}</b></span
            ><span
              >{{ tr('在库 / 在途')
              }}<b>{{
                joinText(
                  [tr(number(stock?.on_hand)), '/', tr(number(stock?.in_transit)), tr('件')],
                  ' ',
                )
              }}</b></span
            ><button class="text-link" @click="emit('open', 'facts')">
              {{ tr('查看来源') }}<AppIcon name="info" />
            </button>
          </div>
          <SpaceSyncStrip />
          <SpaceIssueCard v-if="issue && !ended" :issue="issue" />
          <SpaceChangeCard v-if="mission" />
          <section
            v-if="!issue || ended"
            id="space-plan"
            class="space-target space-slot"
            :class="{ 'target-active': space.isTarget('plan') }"
          >
            <SpacePlanCard
              v-if="mission && canDecide && !ended"
              @confirm="emit('confirm')"
              @open="emit('open', $event)"
            />
            <SpaceOutcomeCard v-else :working="working" />
          </section>
          <SpaceOrdersCard v-if="mission" @open="emit('open', $event)" />
          <SpaceFactsCard @open="emit('open', $event)" @navigate="emit('navigate', $event)" />
          <FollowUpCard
            v-if="mission && !ended"
            @pause="emit('open', 'pause')"
            @resume="attempt(() => shop.control('resume'))"
            @receipt="emit('open', 'receipt')"
            @mission="emit('open', 'mission')"
            @check="attempt(() => shop.requestCheck())"
          />
        </template>
        <SpaceSyncStrip v-else-if="item.result?.calculation || item.mission_request" />
        <SpaceWorkContent
          @open="emit('open', $event)"
          @changed="emit('changed')"
          @converse="converse"
        />
        <SpaceTimelineCard v-if="mission" @open="emit('open', $event)" />
        <div v-if="linked && openAlerts" class="risk-link">
          <button class="text-link" @click="emit('open', 'alerts')">
            {{ joinText([tr(openAlerts), tr('项经营提醒，查看依据')], ' ')
            }}<AppIcon name="chevron-right" />
          </button>
        </div>
        <p v-if="localError" class="notice amber" role="alert">{{ tr(localError) }}</p>
        <footer class="task-footer space-footer">
          <span>{{
            tr(
              linked && !['RECEIVED', 'PROCESSING', 'WAITING_INPUT'].includes(item.status)
                ? '同一委托保留全部决定与执行结果。'
                : '停止助手处理不等于停止备货跟进或取消采购。',
            )
          }}</span>
          <span class="space-footer-actions"
            ><button
              v-if="['RECEIVED', 'PROCESSING', 'WAITING_INPUT'].includes(item.status)"
              class="text-link"
              :disabled="work.s.busy || !!work.s.pending"
              @click="workControl('cancel')"
            >
              {{ tr('停止本轮处理') }}</button
            ><button
              v-if="['BLOCKED', 'CANCELLED'].includes(item.status) || expired"
              class="secondary"
              :disabled="work.s.busy || !!work.s.pending"
              @click="workControl('retry')"
            >
              {{ tr('重新处理这件事') }}</button
            ><button
              v-if="mission && !ended && hasRole('approver')"
              class="text-link"
              :disabled="Boolean(s.busy) || openActions.length > 0 || agent.active.value"
              @click="emit('open', 'complete')"
            >
              {{ tr('结束这项委托') }}
            </button></span
          >
        </footer>
      </div>
      <div class="task-agent-column">
        <SpaceConversationPanel
          ref="conversation"
          @target="highlight($event, true)"
          @changed="emit('changed')"
        />
      </div>
    </div>
  </section>
</template>
