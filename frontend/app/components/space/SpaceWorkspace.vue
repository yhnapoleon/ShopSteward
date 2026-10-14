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
// A business outcome the Agent records while this page is open gets one line above the plan
// card (§4.4). Outcomes already there when the page or the conversation loads stay quiet, and
// a refresh of the same run never brings the line back.
const seenOutcomes = new Set<string>()
const freshOutcome = ref<{ run: string; id: string; kind: 'evaluation' | 'revision' } | null>(
  null,
)
function noteOutcomes(announce: boolean) {
  const run = agent.s.run
  for (const outcome of run?.outcomes || []) {
    const key = run!.id + ':' + outcome.invocation_id
    if (seenOutcomes.has(key)) continue
    seenOutcomes.add(key)
    if (announce && outcome.availability === 'available')
      freshOutcome.value = { run: run!.id, id: outcome.invocation_id, kind: outcome.kind }
  }
}
noteOutcomes(false)
watch(
  () => [agent.s.run?.id, agent.s.run?.outcomes?.length, agent.s.initialized] as const,
  ([, , initialized], [, , wasInitialized]) => noteOutcomes(!!initialized && !!wasInitialized),
)
const outcomeHint = computed(() =>
  freshOutcome.value && freshOutcome.value.run === agent.s.run?.id ? freshOutcome.value : null,
)
async function viewOutcome() {
  const id = outcomeHint.value?.id
  freshOutcome.value = null
  mobilePanel.value = 'agent'
  conversation.value?.show('agent')
  await nextTick()
  if (id)
    document
      .querySelector(`[data-outcome="${CSS.escape(id)}"]`)
      ?.scrollIntoView({ behavior: reduce.value ? 'auto' : 'smooth', block: 'center' })
}
watch(
  () => item.value?.id,
  () => {
    clearTimeout(timer)
    target.value = ''
    localError.value = ''
    freshOutcome.value = null
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
          <div v-if="mission" class="space-agent-hint-slot" role="status">
            <Transition name="space-rise">
              <p v-if="outcomeHint" class="space-agent-hint">
                <AppIcon name="sparkles" /><span class="space-wide">{{
                  tr(
                    outcomeHint.kind === 'evaluation'
                      ? 'Agent 刚给出一份试算结果，见右侧'
                      : 'Agent 刚给出一份修订结果，见右侧',
                  )
                }}</span
                ><span class="space-narrow">{{
                  tr(
                    outcomeHint.kind === 'evaluation'
                      ? 'Agent 刚给出一份试算结果'
                      : 'Agent 刚给出一份修订结果',
                  )
                }}</span
                ><button class="text-link" @click="viewOutcome">
                  {{ tr('查看结果') }}<AppIcon name="arrow-right" /></button
                ><button
                  class="icon-btn space-agent-hint-close"
                  :aria-label="tr('关闭提示')"
                  @click="freshOutcome = null"
                >
                  <AppIcon name="x" />
                </button>
              </p>
            </Transition>
          </div>
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
          @navigate="emit('navigate', $event)"
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
