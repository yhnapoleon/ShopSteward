<script setup lang="ts">
import { motion, useReducedMotion } from 'motion-v'
import { api, query } from '~/utils/api'
import { money, number, when, actionLabel } from '~/utils/presentation'
const props = defineProps<{ issue: string | null; working: boolean; panel?: string }>()
const emit = defineEmits<{
  open: [name: string]
  confirm: []
  back: []
  navigate: [view: string]
}>()
const shop = useShop()
const { s, mission, plan, stock, product, canDecide, hasRole } = shop
const agent = useAgentConversation()
const { status, actions, pending } = useTaskPresentation()
const reduce = useReducedMotion()
const target = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
const previousPlan = ref<import('~/types/models').Schema<'Plan'> | null>(null)
let receiptEpoch = 0
const receiptError = ref('')
async function loadReceipt() {
  const epoch = ++receiptEpoch,
    id = mission.value?.id,
    currentPlan = plan.value
  previousPlan.value = null
  receiptError.value = ''
  if (!id || !currentPlan || currentPlan.plan_version <= 1) return
  try {
    const page = await api<import('~/types/models').Schema<'PlanList'>>(
      `/api/v1/missions/${id}/plans?limit=2`,
    )
    if (epoch !== receiptEpoch || plan.value?.id !== currentPlan.id) return
    if (!page.items.some((p) => p.id === currentPlan.id)) return
    previousPlan.value =
      page.items.find(
        (p) => p.mission_id === id && p.plan_version === currentPlan.plan_version - 1,
      ) || null
  } catch {
    if (epoch === receiptEpoch) receiptError.value = '暂未取得前一版方案，可重试核对版本变化。'
  }
}
watch([agent.scope, () => plan.value?.id], loadReceipt, { immediate: true })
const change = computed(() =>
  previousPlan.value && plan.value ? { from: previousPlan.value, to: plan.value } : null,
)
const ended = computed(() => ['COMPLETED', 'CANCELLED'].includes(mission.value?.status || ''))
const mobilePanel = ref(props.panel === 'agent' ? 'agent' : 'result')
watch(
  () => props.panel,
  (value) => (mobilePanel.value = value === 'agent' ? 'agent' : 'result'),
)
const localError = ref('')
const historicalPlans = ref<import('~/types/models').Schema<'Plan'>[]>([])
const historyLoaded = ref(false)
const historyError = ref('')
const historyCursor = ref<string | null>(null)
const historyLoading = ref(false)
let historyEpoch = 0
watch(
  () => mission.value?.id,
  () => {
    historyEpoch++
    historyCursor.value = null
    historyLoading.value = false
    historicalPlans.value = []
    historyLoaded.value = false
    historyError.value = ''
    localError.value = ''
    target.value = ''
  },
)
async function history(e: Event) {
  if ((e.target as HTMLDetailsElement).open && !historyLoaded.value) await loadPlans()
}
async function loadPlans() {
  if (!mission.value || historyLoading.value) return
  const id = mission.value.id,
    epoch = historyEpoch
  historyLoading.value = true
  historyError.value = ''
  try {
    const page = await api<import('~/types/models').Schema<'PlanList'>>(
      `/api/v1/missions/${id}/plans${query({ limit: 100, cursor: historyCursor.value })}`,
    )
    if (epoch !== historyEpoch) return
    historicalPlans.value = [
      ...new Map([...historicalPlans.value, ...page.items].map((p) => [p.id, p])).values(),
    ]
    historyCursor.value = page.next_cursor
    historyLoaded.value = true
  } catch (e) {
    if (epoch === historyEpoch) historyError.value = (e as Error).message
  } finally {
    if (epoch === historyEpoch) historyLoading.value = false
  }
}
async function highlight(name: string, scroll = false) {
  if (['receipt'].includes(name)) {
    if (scroll) emit('open', 'receipt')
    return
  }
  if (scroll) {
    mobilePanel.value = 'result'
    await nextTick()
  }
  clearTimeout(timer)
  target.value = name
  if (scroll)
    document
      .getElementById('task-' + name)
      ?.scrollIntoView({ behavior: reduce.value ? 'auto' : 'smooth', block: 'center' })
  timer = setTimeout(() => (target.value = ''), 1100)
}
watch(
  () => agent.s.activity?.id,
  () => {
    const activity = agent.s.activity
    if (activity && Date.now() - activity.at < 1500) highlight(activity.target)
  },
)
onUnmounted(() => {
  historyEpoch++
  receiptEpoch++
  clearTimeout(timer)
})
async function recover() {
  localError.value = ''
  try {
    if (props.issue === 'confirmation') await shop.recoverApproval()
    else if (props.issue === 'expired' || props.issue === 'changed') await shop.requestCheck()
    else await shop.refresh(true)
  } catch (e) {
    localError.value = (e as Error).message
  }
}
</script>
<template>
  <section
    v-if="mission"
    class="task-workspace"
    :data-task-id="mission.id"
    :data-mobile-panel="mobilePanel"
  >
    <button class="task-back text-link" @click="emit('back')">
      <AppIcon name="arrow-right" />返回今日
    </button>
    <header
      id="task-mission"
      class="task-page-heading task-target"
      :class="{ 'target-active': target === 'mission' || agent.runningTarget.value === 'mission' }"
    >
      <div>
        <div class="eyebrow">活动备货 · {{ mission.id.slice(-8) }}</div>
        <h1>{{ product?.name || '备货委托' }}</h1>
        <p>{{ mission.objective }}</p>
      </div>
      <div class="task-heading-actions">
        <span class="tag" :class="status.tone">{{ status.label }}</span
        ><button class="text-link" @click="emit('open', 'mission')">委托详情</button>
      </div>
    </header>
    <slot name="intake" />
    <div class="task-mobile-tabs" aria-label="任务内容切换">
      <button :aria-pressed="mobilePanel === 'result'" @click="mobilePanel = 'result'">
        方案与进展</button
      ><button :aria-pressed="mobilePanel === 'agent'" @click="mobilePanel = 'agent'">
        Agent 工作<span v-if="agent.active.value" class="agent-live-dot" />
      </button>
    </div>
    <div class="task-columns">
      <div class="task-result-column">
        <div class="task-fact-summary" aria-label="当前经营事实摘要">
          <span
            >{{ s.connected ? '可用现金' : '上次现金'
            }}<b>{{ money(s.dashboard?.state.available_cash_minor) }}</b></span
          ><span
            >在库 / 在途<b
              >{{ number(stock?.on_hand) }} / {{ number(stock?.in_transit) }} 件</b
            ></span
          ><button class="text-link" @click="emit('open', 'facts')">
            查看来源<AppIcon name="info" />
          </button>
        </div>
        <section
          id="task-plan"
          class="task-target"
          :class="{ 'target-active': target === 'plan' || agent.runningTarget.value === 'plan' }"
        >
          <div class="section-label">
            {{ ended ? '任务结果' : '当前安排'
            }}<span class="right">{{ plan ? `方案 v${plan.plan_version}` : '来自业务记录' }}</span>
          </div>
          <p v-if="receiptError" class="notice amber" role="status">
            {{ receiptError }}<button class="text-link" @click="loadReceipt">重试读取</button>
          </p>
          <Transition name="change-receipt"
            ><div v-if="change" :key="change.to.id" class="plan-change-receipt">
              <AppIcon name="check-check" />
              <div>
                <b>方案版本已更新</b
                ><span
                  v-if="
                    change.from.proposed_purchase?.quantity !==
                    change.to.proposed_purchase?.quantity
                  "
                  >补货 {{ change.from.proposed_purchase?.quantity ?? 0 }} →
                  {{ change.to.proposed_purchase?.quantity ?? 0 }} 件 · v{{
                    change.from.plan_version
                  }}
                  → v{{ change.to.plan_version }}</span
                ><span v-else
                  >方案 v{{ change.from.plan_version }} → v{{ change.to.plan_version }} ·
                  依据已更新</span
                ><small>方案变化不代表已采购，实际执行以回执为准。</small>
              </div>
            </div></Transition
          >
          <article v-if="issue && !ended" class="attention-card glass">
            <span class="tag amber">需要处理</span>
            <h2>
              {{
                issue === 'confirmation'
                  ? '确认结果尚未取得'
                  : issue === 'unknown'
                    ? '采购结果还没有核实'
                    : issue === 'changed'
                      ? '经营情况已变化，方案待更新'
                      : issue === 'expired'
                        ? '原方案已过期'
                        : '暂时无法确认最新经营数据'
              }}
            </h2>
            <p>
              {{
                issue === 'confirmation' || issue === 'unknown'
                  ? '保留原确认与采购记录，先查询结果，避免重复采购。'
                  : '先取得最新结果，再核对适用方案。'
              }}
            </p>
            <button class="primary" :disabled="Boolean(s.busy)" @click="recover">
              {{
                issue === 'confirmation'
                  ? '查询原确认结果'
                  : issue === 'expired' || issue === 'changed'
                    ? '重新检查'
                    : '刷新原记录'
              }}
            </button>
            <p v-if="localError" class="notice amber" role="alert">{{ localError }}</p>
          </article>
          <DecisionCard
            v-else-if="canDecide && !ended"
            @confirm="emit('confirm')"
            @evidence="emit('open', 'evidence')"
            @compare="emit('open', 'compare')"
            @mission="emit('open', 'mission')"
          />
          <article v-else class="task-outcome glass">
            <span class="task-outcome-icon"
              ><AppIcon :name="ended ? 'check-check' : pending ? 'clock' : 'orbit'"
            /></span>
            <div>
              <h2>
                {{
                  ended
                    ? mission.status === 'COMPLETED'
                      ? '这项委托已完成'
                      : '这项委托已取消'
                    : working
                      ? '正在核实采购提交'
                      : '暂时没有新的决定'
                }}
              </h2>
              <p>{{ status.detail }}</p>
              <button v-if="actions.length" class="text-link" @click="emit('open', 'receipt')">
                查看采购与到货记录<AppIcon name="arrow-up-right" />
              </button>
            </div>
          </article>
        </section>
        <section
          id="task-facts"
          class="task-facts glass task-target"
          :class="{ 'target-active': target === 'facts' || agent.runningTarget.value === 'facts' }"
          aria-label="任务经营事实"
        >
          <div class="task-section-heading">
            <h2>经营事实</h2>
            <button class="text-link" @click="emit('navigate', 'overview')">
              经营概览<AppIcon name="arrow-up-right" />
            </button>
            <button class="text-link" @click="emit('open', 'facts')">
              {{
                s.connected && s.dashboard?.freshness.status === 'FRESH'
                  ? '查看数据来源'
                  : '数据待核实'
              }}<AppIcon name="database" />
            </button>
          </div>
          <dl>
            <div>
              <dt>
                {{
                  s.connected && s.dashboard?.freshness.status === 'FRESH'
                    ? '可用现金'
                    : '上次已核实现金'
                }}
              </dt>
              <dd data-testid="cash">{{ money(s.dashboard?.state.available_cash_minor) }}</dd>
            </div>
            <div>
              <dt>在库</dt>
              <dd>
                <span data-testid="stock">{{ number(stock?.on_hand) }}</span
                ><small>件</small>
              </dd>
            </div>
            <div>
              <dt>采购在途</dt>
              <dd>
                <span data-testid="inbound">{{ number(stock?.in_transit) }}</span
                ><small>件</small>
              </dd>
            </div>
            <div>
              <dt>待结算</dt>
              <dd data-testid="receivables">{{ money(s.dashboard?.state.receivables_minor) }}</dd>
            </div>
          </dl>
          <p class="source-note">
            {{ when(s.dashboard?.freshness.last_sync_at) }} · 待结算资金尚未到账
          </p>
        </section>
        <FollowUpCard
          v-if="!ended"
          @pause="emit('open', 'pause')"
          @resume="shop.control('resume').catch((e) => (localError = e.message))"
          @receipt="emit('open', 'receipt')"
          @mission="emit('open', 'mission')"
          @check="shop.requestCheck().catch((e) => (localError = e.message))"
        />
        <section
          id="task-history"
          class="task-history task-target"
          :class="{
            'target-active': target === 'history' || agent.runningTarget.value === 'history',
          }"
        >
          <div class="task-section-heading">
            <h2>任务记录</h2>
            <button
              class="text-link"
              aria-label="本次经营简报 已做的决定、实际结果与下一步"
              @click="emit('open', 'brief')"
            >
              保存经营简报<AppIcon name="file-text" />
            </button>
          </div>
          <ol class="task-timeline">
            <li v-for="item in s.timeline.slice(0, 6)" :key="item.id">
              <span class="task-timeline-dot" />
              <div>
                <p>{{ item.summary }}</p>
                <time>{{ when(item.created_at) }}</time>
              </div>
            </li>
          </ol>
          <details v-if="s.timeline.length > 6 || s.timelineCursor" class="task-earlier">
            <summary>查看更早记录</summary>
            <p v-for="item in s.timeline.slice(6)" :key="item.id">
              {{ when(item.created_at) }} · {{ item.summary }}
            </p>
            <button
              v-if="s.timelineCursor"
              class="text-link"
              @click="shop.moreTimeline().catch((e) => (localError = e.message))"
            >
              加载更早记录
            </button>
          </details>
          <details class="task-earlier" @toggle="history">
            <summary>历次方案与决定</summary>
            <p v-if="historyError" role="alert">{{ historyError }}</p>
            <article v-for="p in historicalPlans" :key="p.id" class="task-plan-record">
              <b
                >方案 v{{ p.plan_version }} ·
                {{
                  {
                    PENDING_APPROVAL: '待审批',
                    APPROVED: '已批准',
                    REJECTED: '本轮不采购',
                    SUPERSEDED: '已被后续方案取代',
                    EXPIRED: '已过期',
                  }[p.status]
                }}</b
              >
              <p>建议 {{ p.proposed_purchase?.quantity ?? 0 }} 件 · {{ when(p.created_at) }}</p>
              <p v-for="a in actions.filter((a) => a.plan_id === p.id)" :key="a.id">
                采购 {{ a.quantity }} 件 · {{ actionLabel(a.status) }}
              </p>
            </article>
            <p v-if="historyLoaded && !historicalPlans.length">暂无方案记录。</p>
            <button
              v-if="historyCursor || historyError"
              class="text-link"
              :disabled="historyLoading"
              @click="loadPlans"
            >
              {{ historyError ? '重试读取方案' : '加载更早方案' }}
            </button>
          </details>
        </section>
        <div v-if="s.alerts.some((a) => a.status === 'OPEN')" class="risk-link">
          <button class="text-link" @click="emit('open', 'alerts')">
            {{ s.alerts.filter((a) => a.status === 'OPEN').length }} 项经营提醒，查看依据<AppIcon
              name="chevron-right"
            />
          </button>
        </div>
        <p v-if="localError" class="notice amber" role="alert">{{ localError }}</p>
        <footer class="task-footer">
          <span>同一任务保留全部决定与执行结果。</span
          ><button
            v-if="!ended && hasRole('approver')"
            class="text-link"
            :disabled="Boolean(s.busy) || !!pending || agent.active.value"
            @click="emit('open', 'complete')"
          >
            结束这项委托
          </button>
        </footer>
      </div>
      <motion.div
        class="task-agent-column"
        :initial="reduce ? false : { opacity: 0, y: 8 }"
        :animate="{ opacity: 1, y: 0 }"
        :transition="{ duration: reduce ? 0 : 0.28 }"
        ><slot name="assistant"><AgentWorkspace @target="highlight($event, true)" /></slot
      ></motion.div>
    </div>
  </section>
</template>
