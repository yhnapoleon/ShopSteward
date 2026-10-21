<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { useReducedMotion } from 'motion-v'
import { money, number } from '~/utils/presentation'
import { alertCount, supplierDisplayName } from '~/utils/glossary'
import { named } from '~/utils/recovery'
import type { Schema } from '~/types/models'

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
const { s, stock, canDecide, hasRole, awaitingSupplier } = shop
const work = useWorkItems()
const agent = useAgentConversation()
const space = useSpace()
const { item, linked, mission, ended, openActions, target } = space
const reduce = useReducedMotion()
// This mission's own order, sent by the owner and not yet answered by the supplier.
const sentByHand = computed(
  () => !!mission.value && awaitingSupplier.value?.mission_id === mission.value.id,
)
// The supplier declined that order: its receipt keeps the slot until the page has synced once
// more, then the slot moves on (the order row keeps saying the supplier declined).
const declined = ref<Schema<'Action'> | null>(null)
watch(
  () => awaitingSupplier.value?.id,
  (now, before) => {
    const answered = before && !now ? s.actions.find((a) => a.id === before) : undefined
    declined.value = answered?.supplier_reply?.outcome === 'declined' ? answered : null
  },
)
let declinedSynced = false
watch(
  () => s.refreshing,
  (refreshing) => {
    if (refreshing) declinedSynced = !!declined.value
    else if (declinedSynced && s.connected) declined.value = null
  },
)
const { rechecking, blocking } = usePlanRecheck(() => props.issue)
// An emergency restock under way shows its own plan, order and arrival in its card (§18); the
// slots below then stay out of the way instead of repeating them.
const launcher = useRecoveryLaunch()
const owned = computed(() => launcher.owned(mission.value?.id))
const restocking = computed(() => launcher.inProgress(mission.value?.id))
const flowOwnsSlot = computed(() => {
  if (!owned.value) return false
  // The restock card already says what the mission waits for; only another decision (a regular
  // plan, an order outside the restock) still earns the plan slot.
  const ownPlan = !!owned.value.planId && shop.plan.value?.id === owned.value.planId
  // Its order: the one it shows, any of its purchases, or the one its plan just led to (the
  // backend creates it as the plan is confirmed, before the card has read the Case again).
  const waiting = awaitingSupplier.value
  const ownOrder =
    !!waiting &&
    (waiting.id === owned.value.actionId ||
      !!owned.value.actionIds?.includes(waiting.id) ||
      (!!owned.value.planId && waiting.plan_id === owned.value.planId))
  const otherOrder = sentByHand.value && !ownOrder
  const otherPlan = !!mission.value && canDecide.value && !ownPlan
  return !otherOrder && !otherPlan
})
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
const freshOutcome = ref<{ run: string; id: string; kind: 'evaluation' | 'revision' } | null>(null)
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
    declined.value = null
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
const canStop = computed(() =>
  ['RECEIVED', 'PROCESSING', 'WAITING_INPUT'].includes(item.value?.status || ''),
)
const canRetry = computed(
  () => ['BLOCKED', 'CANCELLED'].includes(item.value?.status || '') || expired.value,
)
const canEnd = computed(() => !!mission.value && !ended.value && hasRole('approver'))
</script>
<template>
  <section
    v-if="item"
    class="space-workspace"
    :class="{ 'task-workspace': !!mission }"
    :data-task-id="item.mission_id || item.id"
    :data-mobile-panel="mobilePanel"
  >
    <SpaceHeader :issue="blocking" @back="emit('back')" @open="emit('open', $event)" />
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
          <RecoveryFlow
            v-if="mission && s.session?.recoveryCases"
            :key="mission.id"
            :mission-id="mission.id"
            @confirm="emit('confirm')"
          />
          <SpaceSyncStrip />
          <!-- The arrival card leaves out every purchase of a restock under way: its card records
               them and says when recording the last one ends the restock (useShop.awaitingArrival).
               A plan to confirm keeps the one primary action; recording then steps back. -->
          <ArrivalCard
            v-if="mission"
            :quiet="restocking || (!!mission && canDecide && !ended && !!shop.plan.value)"
          />
          <!-- While a restock leads the page its card holds the one primary action. -->
          <SpaceIssueCard v-if="blocking && !ended" :issue="blocking" :quiet="restocking" />
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
            v-if="(!blocking || ended) && !flowOwnsSlot"
            id="space-plan"
            class="space-target space-slot"
            :class="{ 'target-active': space.isTarget('plan') }"
          >
            <p v-if="rechecking && !ended" class="space-recheck" role="status">
              <span class="space-pulse" aria-hidden="true" />{{ tr('正在重新核对方案…') }}
            </p>
            <!-- An order the owner sends by hand waits here for the supplier's reply. -->
            <AssistedOrderCard v-if="sentByHand && !ended" :quiet="restocking" />
            <article v-else-if="declined && !ended" class="assisted-order glass">
              <span class="tag amber">{{ tr('供应商拒单') }}</span>
              <h2>
                {{
                  named('{0}拒单了', [supplierDisplayName(declined.purchase_snapshot.supplier_id)])
                }}
              </h2>
              <SupplierReceipt v-if="declined.supplier_reply" :reply="declined.supplier_reply" />
            </article>
            <!-- One primary per screen: while an emergency restock leads the page (before a plan
                 is adopted from it), a regular plan that can still be confirmed steps back to one
                 line. Once the owner decides in the restock, routine checks leave the item alone. -->
            <p
              v-else-if="restocking && mission && canDecide && !ended && shop.plan.value"
              class="rf-regular-plan"
              data-regular-plan-line
            >
              <span>{{
                tr('常规方案：建议补 {0} 件 · {1}', [
                  shop.plan.value.proposed_purchase?.quantity ?? 0,
                  money(shop.plan.value.proposed_purchase?.total_minor),
                ])
              }}</span
              ><button class="text-link" @click="emit('confirm')">
                {{ tr('核对 {0} 件采购', [shop.plan.value.proposed_purchase?.quantity ?? 0])
                }}<AppIcon name="chevron-right" />
              </button>
            </p>
            <SpacePlanCard
              v-else-if="mission && (canDecide || rechecking) && !ended"
              :held="rechecking"
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
            {{ alertCount(openAlerts) }}<AppIcon name="chevron-right" />
          </button>
        </div>
        <p v-if="localError" class="notice amber" role="alert">{{ tr(localError) }}</p>
        <footer v-if="canStop || canRetry || canEnd" class="task-footer space-footer">
          <span class="space-footer-actions"
            ><button
              v-if="canStop"
              class="text-link"
              :disabled="work.s.busy || !!work.s.pending"
              @click="workControl('cancel')"
            >
              {{ tr('停止本轮处理') }}</button
            ><button
              v-if="canRetry"
              class="secondary"
              :disabled="work.s.busy || !!work.s.pending"
              @click="workControl('retry')"
            >
              {{ tr('重新处理这件事') }}</button
            ><button
              v-if="canEnd"
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
