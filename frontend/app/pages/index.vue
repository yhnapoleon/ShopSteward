<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { api } from '~/utils/api'
import { money, number, when, actionLabel, reasonLabel } from '~/utils/presentation'
import { downloadFile } from '~/utils/quotations'
import { workPresentation } from '~/utils/workPresentation'
const { locale, setLocale, preferenceError } = useLocale()
const scheduleSaving = ref(false)
const scheduleNotice = ref('')
const scheduleUncertainId = ref('')
const shop = useShop()
const { s, mission, stock, product, plan, unresolved, canDecide, hasRole } = shop
const agent = useAgentConversation(true)
const work = useWorkItems(true)
const activeWorks = computed(() =>
  work.s.items
    .filter(
      (i) =>
        i.business?.needs_attention ||
        ['QUEUED', 'EXECUTING'].includes(i.business?.code || '') ||
        ['RECEIVED', 'PROCESSING', 'WAITING_INPUT', 'BLOCKED'].includes(i.status) ||
        (i.mission
          ? !['COMPLETED', 'CANCELLED'].includes(i.mission.status)
          : !['COMPLETED', 'CANCELLED'].includes(i.status)),
    )
    .sort((a, b) => workPresentation(a).priority - workPresentation(b).priority),
)
const taskRouteError = ref('')
const viewScroll: Record<string, number> = {}
const route = useRoute(),
  router = useRouter()
const view = computed(() =>
  ['today', 'following', 'journal', 'overview', 'documents', 'task', 'work'].includes(
    String(route.query.view),
  )
    ? String(route.query.view)
    : 'today',
)
const dialog = ref(''),
  modalError = ref(''),
  deck = ref(false),
  token = ref(''),
  scheduleSeconds = ref(30),
  recordFilter = ref('business')
const approval = ref<{ plan: Schema<'Plan'>; quantity: number } | null>(null)
watch(
  () => s.storeId,
  (_id, previous) => {
    if (!previous) return
    approval.value = null
    dialog.value = ''
    deck.value = false
    taskRouteError.value = ''
    if (['task', 'work'].includes(view.value)) void router.replace({ query: { view: 'today' } })
  },
)
let poll: ReturnType<typeof setInterval> | undefined
let noticeTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => s.notice,
  (value) => {
    if (noticeTimer) clearTimeout(noticeTimer)
    if (value)
      noticeTimer = setTimeout(() => {
        s.notice = ''
      }, 4000)
  },
)
onMounted(async () => {
  await shop.init(typeof route.query.store === 'string' ? route.query.store : undefined)
  if (view.value === 'task' && typeof route.query.mission === 'string') {
    await shop.selectMission(route.query.mission)
    if (mission.value?.id !== route.query.mission)
      taskRouteError.value = '无法读取这项任务，请返回今日选择可见任务。'
  }
  if (view.value === 'work' && typeof route.query.item === 'string')
    await openWork(route.query.item)
  poll = setInterval(() => void shop.pollEnvironment(), 2500)
})
onUnmounted(() => {
  if (poll) clearInterval(poll)
  if (noticeTimer) clearTimeout(noticeTimer)
})
function open(name: string) {
  modalError.value = ''
  scheduleNotice.value = ''
  dialog.value = name
  scheduleSeconds.value = mission.value?.schedule.interval_seconds || 30
}
async function navigate(next: string) {
  viewScroll[view.value] = window.scrollY
  dialog.value = ''
  await router.push({ query: { view: next } })
  await nextTick()
  window.scrollTo({ top: viewScroll[next] || 0 })
}
async function openWork(id: string) {
  dialog.value = ''
  taskRouteError.value = ''
  await work.select(id)
  await syncWork()
}
async function syncWork() {
  const item = work.s.detail?.item,
    epoch = work.s.epoch
  if (!item || item.store_id !== s.storeId) return
  if (item.mission_id && s.missionId !== item.mission_id) await shop.selectMission(item.mission_id)
  if (epoch !== work.s.epoch || work.s.detail?.item.id !== item.id || item.store_id !== s.storeId)
    return
  await router.push({ query: { view: 'work', item: item.id, store: item.store_id } })
}
watch(
  () => route.query.item,
  (id) => {
    if (view.value === 'work' && typeof id === 'string' && id !== work.s.selected) void openWork(id)
  },
)
watch(
  () => work.s.detail?.item.mission_id,
  (id) => {
    if (id && view.value === 'work') void syncWork()
  },
)
watch(
  () => work.s.detail?.item.id,
  (id) => {
    if (id && view.value === 'work' && route.query.item !== id) void syncWork()
  },
)
async function openTask(id = mission.value?.id, panel = 'result') {
  if (!id) return
  if (work.s.available) {
    const d = await work.fromMission(id)
    if (d) await syncWork()
    return
  }
  viewScroll[view.value] = window.scrollY
  dialog.value = ''
  taskRouteError.value = ''
  if (id !== s.missionId) await shop.selectMission(id)
  await router.push({ query: { view: 'task', mission: id, store: s.storeId, panel } })
  await nextTick()
  window.scrollTo({ top: 0 })
}
watch(
  () => route.query.mission,
  async (id) => {
    if (view.value === 'task' && typeof id === 'string' && s.storeId && id !== s.missionId) {
      await shop.selectMission(id)
      taskRouteError.value =
        mission.value?.id === id ? '' : '无法读取这项任务，请返回今日选择可见任务。'
    }
  },
)
watch(
  () => mission.value?.id,
  (id) => {
    if (id && id === route.query.mission) taskRouteError.value = ''
  },
)
async function act(fn: () => Promise<unknown>, close = false) {
  modalError.value = ''
  try {
    await fn()
    if (close) dialog.value = ''
  } catch (e) {
    modalError.value = (e as Error).message
  }
}
async function prepare() {
  await act(async () => {
    approval.value = await shop.prepareDecision()
    open('approval')
  })
}
async function submit() {
  if (!approval.value) return
  try {
    await shop.decide(approval.value)
    dialog.value = ''
  } catch (e) {
    if (s.pending) dialog.value = ''
    else modalError.value = (e as Error).message
  }
}
async function start() {
  if (mission.value && ['ACTIVE', 'PAUSED'].includes(mission.value.status)) {
    void openTask()
    return
  }
  await act(() => shop.startMission())
  if (mission.value) await openTask()
}
async function connect() {
  await act(async () => {
    await $fetch('/api/session', { method: 'POST', body: { token: token.value } })
    token.value = ''
    await shop.init()
  }, true)
}
function applySchedule(id: string, saved: Schema<'Schedule'>) {
  if (mission.value?.id !== id || saved.mission_id !== id) return
  if (saved.version >= mission.value.schedule.version) mission.value.schedule = saved
  scheduleSeconds.value = mission.value.schedule.interval_seconds
  scheduleUncertainId.value = ''
}
async function verifySchedule() {
  const current = mission.value
  if (!current || scheduleSaving.value) return
  scheduleSaving.value = true
  modalError.value = ''
  try {
    const latest = await api<Schema<'Mission'>>(`/api/v1/missions/${current.id}`)
    if (mission.value?.id !== current.id || s.storeId !== current.store_id) return
    applySchedule(current.id, latest.schedule)
    scheduleNotice.value = '已核对当前安排'
  } catch (e) {
    if (mission.value?.id === current.id) modalError.value = (e as Error).message
  } finally {
    scheduleSaving.value = false
  }
}
async function saveSchedule(event: Event) {
  const current = mission.value
  const selected = Number((event.target as HTMLSelectElement).value)
  if (
    !current ||
    scheduleSaving.value ||
    scheduleUncertainId.value === current.id ||
    !hasRole('operator')
  )
    return
  if (!Number.isInteger(selected) || selected < 5 || selected > 3600) return
  const sameTask = () => mission.value?.id === current.id && s.storeId === current.store_id
  if (selected === current.schedule.interval_seconds) return
  scheduleSaving.value = true
  scheduleNotice.value = ''
  modalError.value = ''
  try {
    const saved = await api<Schema<'Schedule'>>(
      `/api/v1/missions/${current.id}/schedule`,
      'PATCH',
      {
        interval_seconds: selected,
        enabled: current.schedule.enabled,
        expected_schedule_version: current.schedule.version,
      } satisfies Schema<'ScheduleUpdate'>,
    )
    if (!sameTask()) return
    applySchedule(current.id, saved)
    scheduleNotice.value = '已自动保存'
    // The acknowledged schedule is authoritative even if another overview read fails.
    await shop.refresh(true)
  } catch (e) {
    if (!sameTask()) return
    modalError.value = (e as Error).message
    scheduleUncertainId.value = current.id
    try {
      const latest = await api<Schema<'Mission'>>(`/api/v1/missions/${current.id}`)
      if (sameTask()) applySchedule(current.id, latest.schedule)
    } catch {
      // Do not show the old value as a rollback when the server may have committed.
      if (sameTask()) scheduleNotice.value = '保存结果尚未核实，请重新核对安排。'
    }
  } finally {
    scheduleSaving.value = false
  }
}

const title = computed(
  () =>
    ({
      today: s.storeId ? '今天的经营安排。' : '从示例店铺开始。',
      following: '持续跟进',
      journal: '经营记录',
      overview: '经营概览',
      documents: '文档中心',
      task: '任务工作区',
      work: '事项工作区',
    })[view.value],
)
const issue = computed(() =>
  s.pending
    ? 'confirmation'
    : unresolved.value?.status === 'UNKNOWN'
      ? 'unknown'
      : !s.connected && s.storeId
        ? 'offline'
        : s.dashboard && s.dashboard.freshness.status !== 'FRESH'
          ? 'stale'
          : plan.value?.status === 'EXPIRED'
            ? 'expired'
            : plan.value?.status === 'PENDING_APPROVAL' &&
                s.dashboard &&
                plan.value.state_version !== s.dashboard.state.state_version &&
                !unresolved.value
              ? 'changed'
              : null,
)
const working = computed(
  () => unresolved.value && ['QUEUED', 'EXECUTING'].includes(unresolved.value.status),
)
const decisionCount = computed(() => (issue.value || canDecide.value ? 1 : 0))
const receiptActions = computed(() =>
  s.actions.filter((a) => !mission.value || a.mission_id === mission.value.id),
)
const recordItems = computed(() =>
  recordFilter.value === 'decisions'
    ? s.timeline.filter((t) => t.actor_type === 'USER')
    : s.timeline,
)
const labels: Record<string, string> = {
  approval: '核对这笔采购',
  evidence: '当前选择的依据',
  compare: '比较补货候选',
  receipt: '采购与到货记录',
  mission: '这项备货委托',
  pause: '暂停主动跟进？',
  complete: '结束这项委托？',
  settings: '设置',
  controls: '联调控制 · 合成经营环境',
  facts: '当前账目与来源',
  brief: '本次经营简报',
  quote: '整理供应商报价',
  simulation: '先试算补货',
  connection: '连接后端身份',
  alerts: '需要关注的事项',
}
function briefing() {
  return [
    `ShopSteward｜经营简报`,
    `商品：${product.value?.name || '未取得'}`,
    `经营时点：${when(s.dashboard?.state.simulation_time)}`,
    `可用现金：${money(s.dashboard?.state.available_cash_minor)}`,
    `在库：${number(stock.value?.on_hand)} 件；在途：${number(stock.value?.in_transit)} 件`,
    `待结算：${money(s.dashboard?.state.receivables_minor)}（未回款）`,
    `剩余需求假设：${number(stock.value?.remaining_demand)} 件`,
    `任务状态：${mission.value?.status || '尚未建立'}`,
    `最近检查：${when(s.dashboard?.last_check_at)}`,
    `下一检查：${when(mission.value?.schedule.next_run_at)}`,
    '',
    ...s.timeline.map((t) => when(t.created_at) + ' ' + t.summary),
    '',
    '以上来源于业务API；当前为合成经营环境，备货到位不代表活动结束。',
  ]
    .map((line) => tr(line))
    .join('\n')
}
</script>
<template>
  <div class="app">
    <header class="app-header">
      <div class="brand">
        <span class="brand-mark"><AppIcon name="layers-2" /></span><span>ShopSteward</span>
      </div>
      <nav class="nav" :aria-label="tr('主导航')">
        <button
          v-for="(label, id) in { today: '今日', following: '持续跟进', journal: '经营记录' }"
          :key="id"
          :class="{ active: view === id }"
          :aria-current="view === id ? 'page' : undefined"
          @click="navigate(id)"
        >
          <AppIcon
            :name="{ today: 'panels-top-left', following: 'orbit', journal: 'notebook-pen' }[id]"
          /><span>{{ tr(label) }}</span
          ><span v-if="id === 'today' && decisionCount" class="count">{{ tr(decisionCount) }}</span>
        </button>
      </nav>
      <button
        v-if="mission"
        class="global-agent-entry"
        :class="{ 'is-running': agent.running.value }"
        :aria-label="tr('查看Agent工作区')"
        @click="openTask(undefined, 'agent')"
      >
        <span class="agent-live-dot" /><span>{{
          tr(agent.active.value || agent.s.syncError ? agent.status.value : 'Agent 工作区')
        }}</span
        ><AppIcon name="arrow-up-right" />
      </button>
      <div class="header-store">
        <button class="icon-btn settings-entry" :aria-label="tr('设置')" @click="open('settings')">
          <AppIcon name="sliders-horizontal" />
        </button>
        <button class="store-switch" @click="open('controls')">
          <span class="avatar">{{ tr('店') }}</span
          ><span
            ><strong>{{
              tr(
                s.storeId
                  ? s.storeId === s.activeStoreId
                    ? '当前经营环境'
                    : '历史场景'
                  : '选择店铺',
              )
            }}</strong
            ><small>{{ tr('我的经营空间') }}</small></span
          ><AppIcon name="chevron-down" />
        </button>
      </div>
    </header>
    <main class="workspace">
      <button
        class="icon-btn mobile-settings-entry"
        :aria-label="tr('设置')"
        @click="open('settings')"
      >
        <AppIcon name="sliders-horizontal" />
      </button>
      <button
        v-if="mission"
        class="mobile-agent-entry"
        :aria-label="tr('移动端Agent工作区')"
        @click="openTask(undefined, 'agent')"
      >
        <span class="agent-live-dot" :class="{ 'is-running': agent.running.value }" />{{
          tr(agent.active.value || agent.s.syncError ? agent.status.value : '查看任务与 Agent')
        }}<AppIcon name="arrow-up-right" />
      </button>
      <header v-if="!['overview', 'documents'].includes(view)" class="topbar">
        <div class="breadcrumb">
          {{ tr('我的经营空间') }}<AppIcon name="chevron-right" /><b>{{
            tr(
              {
                today: '今日',
                following: '持续跟进',
                journal: '经营记录',
                task: '任务工作区',
                work: '事项工作区',
              }[view],
            )
          }}</b>
        </div>
        <div class="mobile-header">
          <span class="brand-mark"><AppIcon name="layers-2" /></span>ShopSteward
        </div>
        <div class="top-actions">
          <button class="demo-badge" @click="open('controls')">
            {{ tr('联调控制 · 合成数据') }}</button
          ><span class="top-clock">{{ tr(when(s.dashboard?.state.simulation_time)) }}</span
          ><button class="icon-btn" :aria-label="tr('设置')" @click="open('settings')">
            <AppIcon name="sliders-horizontal" />
          </button>
        </div>
      </header>
      <div v-if="!['overview', 'documents', 'task', 'work'].includes(view)" class="page-head">
        <div>
          <div class="eyebrow">{{ tr(s.connected ? '业务接口已连接' : '经营空间') }}</div>
          <h1>{{ tr(title) }}</h1>
          <p>
            {{
              tr(
                view === 'today'
                  ? '需要拍板的事情固定放在这里；其余进度按需查看。'
                  : view === 'following'
                    ? '看到原委托、已完成的动作和下一步。'
                    : '事实、决定与整理结果，都可以回来核对。',
              )
            }}
          </p>
        </div>
        <div class="page-head-actions">
          <button
            v-if="s.session?.quantitySimulation && s.storeId"
            class="secondary"
            @click="open('simulation')"
          >
            {{ tr('先试算补货') }}
          </button>
          <button
            class="quiet-button"
            :aria-label="tr('交给我一件事')"
            :disabled="s.loading"
            @click="deck = true"
          >
            <AppIcon name="plus" /><span>{{ tr('交给我一件事') }}</span>
          </button>
        </div>
      </div>
      <p
        v-if="s.error && !dialog && !['overview', 'documents'].includes(view)"
        class="notice amber"
        role="alert"
      >
        {{ tr(s.error) }}
        <button class="text-link" @click="act(() => shop.refresh(true))">
          {{ tr('刷新状态') }}
        </button>
      </p>
      <p
        v-if="(work.s.syncError || work.s.listError || work.s.error) && view !== 'work'"
        class="notice amber"
        role="alert"
      >
        {{ tr(work.s.syncError || work.s.listError || work.s.error) }}
      </p>
      <div v-if="s.loading" class="empty-decision glass" role="status">
        {{ tr('正在读取经营数据…') }}
      </div>
      <div v-else-if="!s.session?.authenticated" class="start-card glass">
        <h2>{{ tr('先连接后端用户身份。') }}</h2>
        <p>{{ tr('使用本机开发环境提供的用户凭证。凭证不会放入浏览器本地存储。') }}</p>
        <button class="primary" @click="open('connection')">{{ tr('连接后端') }}</button>
      </div>
      <BusinessOverview
        v-else-if="view === 'overview'"
        @navigate="navigate"
        @controls="open('controls')"
      />
      <LazyDocumentCenter
        v-else-if="view === 'documents'"
        :key="s.storeId + ':' + s.session.principal_id + ':' + s.session.roles.join(',')"
        :store-id="s.storeId"
        :session="s.session"
        :catalog="s.catalog"
        @navigate="navigate"
      />
      <WorkWorkspace
        v-else-if="view === 'work'"
        :issue="issue"
        :working="Boolean(working)"
        @open="open"
        @confirm="prepare"
        @back="navigate('today')"
        @navigate="navigate"
        @changed="syncWork"
      />
      <TaskWorkspace
        v-else-if="view === 'task' && mission && !taskRouteError"
        :issue="issue"
        :working="Boolean(working)"
        :panel="String(route.query.panel || 'result')"
        @open="open"
        @confirm="prepare"
        @navigate="navigate"
        @back="navigate('today')"
      />
      <section v-else-if="view === 'task' && s.pending" class="attention-card glass">
        <h2>{{ tr('确认结果尚未取得') }}</h2>
        <p>{{ tr('采购请求可能已经受理。查询沿用原确认编号，不创建另一笔采购。') }}</p>
        <button
          class="primary"
          :disabled="Boolean(s.busy)"
          @click="act(() => shop.recoverApproval())"
        >
          {{ tr('查询原确认结果') }}
        </button>
      </section>
      <section v-else-if="view === 'task'" class="task-missing glass">
        <h1>{{ tr('这项任务暂时不可用') }}</h1>
        <p>{{ tr(taskRouteError || s.error || '请选择当前身份可以查看的任务。') }}</p>
        <button class="primary" @click="navigate('today')">{{ tr('返回今日') }}</button>
      </section>
      <div v-else class="content-grid">
        <section class="main-column">
          <div v-if="view === 'today'" id="decision-zone">
            <div class="section-label">
              {{ tr(work.s.available ? '正在处理的事情' : '需要你决定')
              }}<span class="small-count">{{
                tr(
                  work.s.available
                    ? activeWorks.length +
                        (mission && !work.s.items.some((i) => i.mission_id === mission?.id) ? 1 : 0)
                    : decisionCount,
                )
              }}</span
              ><span class="right">{{ tr('每笔采购单独确认') }}</span>
            </div>
            <template v-if="work.s.available">
              <p v-if="work.s.syncError" class="notice amber" role="alert">
                {{ tr(work.s.syncError) }}
              </p>
              <WorkCard
                v-for="item in activeWorks"
                :key="item.id"
                :item="item"
                @open="openWork(item.id)"
              />
              <div v-if="!mission && !activeWorks.length" class="work-intake-inline glass">
                <WorkIntake @submitted="openWork" />
              </div>
              <button v-if="work.s.cursor" class="text-link" @click="work.list(true)">
                {{ tr('查看更早事项') }}
              </button>
            </template>
            <TaskCard
              v-if="mission && !work.s.items.some((i) => i.mission_id === mission?.id)"
              @open="openTask()"
            />
            <article v-else-if="!s.storeId" class="start-card glass">
              <span class="tag">{{ tr('从示例店铺开始') }}</span>
              <h2>{{ tr('先准备这一轮经营资料。') }}</h2>
              <p>{{ tr('创建独立SC-01场景，或选择当前身份可以查看的已有店铺。不重置旧数据。') }}</p>
              <button
                class="primary"
                :disabled="!s.session.devTools || Boolean(s.busy)"
                @click="act(() => shop.createScenario())"
              >
                {{ tr('创建示例店铺') }}
              </button>
              <p class="channel-note">
                {{ tr('创建场景不会产生采购。没有开发权限时请由管理员准备。') }}
              </p>
            </article>
            <article v-else-if="issue" class="attention-card glass">
              <span class="tag amber">{{ tr('需要处理') }}</span>
              <h2>
                {{
                  tr(
                    issue === 'confirmation'
                      ? s.pending?.storeId !== s.storeId
                        ? '历史场景的确认结果尚未取得'
                        : '确认结果尚未取得'
                      : issue === 'unknown'
                        ? '采购结果还没有核实'
                        : issue === 'expired'
                          ? '原方案已过期'
                          : '暂时无法确认最新经营数据',
                  )
                }}
              </h2>
              <p>
                {{
                  tr(
                    issue === 'confirmation'
                      ? '可能已经受理。查询会沿用原确认编号，不创建另一笔采购。'
                      : issue === 'unknown'
                        ? '后台正在核实原采购。不要用新采购代替查询，现金预留与原动作仍保留。'
                        : issue === 'expired'
                          ? '先重新检查适用条件，再核对新方案。'
                          : '保留上次结果供参考，恢复数据前不允许确认采购。',
                  )
                }}
              </p>
              <button
                class="primary"
                :disabled="Boolean(s.busy)"
                @click="
                  act(
                    issue === 'confirmation'
                      ? () => shop.recoverApproval()
                      : issue === 'expired'
                        ? () => shop.requestCheck()
                        : () => shop.refresh(true),
                  )
                "
              >
                {{
                  tr(
                    issue === 'confirmation'
                      ? '查询原确认结果'
                      : issue === 'expired'
                        ? '重新检查'
                        : '刷新原记录',
                  )
                }}
              </button>
            </article>
            <article v-else-if="!mission && !work.s.available" class="start-card glass">
              <span class="tag">{{ tr('从示例店铺开始') }}</span>
              <h2>{{ tr('先把这次备货交代清楚。') }}</h2>
              <p>
                {{ tr('查看库存与现金，比较补货安排；每笔采购由你确认，之后跟进到货和需求变化。') }}
              </p>
              <div class="start-scope">
                <b>{{ product?.name }}</b
                ><span>{{
                  joinText([
                    tr('库存'),
                    tr(number(stock?.on_hand)),
                    tr('件 · 现金'),
                    tr(money(s.dashboard?.state.available_cash_minor)),
                  ])
                }}</span
                ><span>{{ tr('建议现金底线¥300 · 采购条件来自当前场景') }}</span>
              </div>
              <button class="primary" :disabled="!hasRole('operator')" @click="deck = true">
                {{ tr('开始备货跟进') }}<AppIcon name="arrow-right" />
              </button>
              <p class="channel-note">{{ tr('尚未建立委托，也没有采购。') }}</p>
            </article>
          </div>
          <template v-if="work.s.available && view === 'following'"
            ><WorkCard
              v-for="item in activeWorks"
              :key="item.id"
              :item="item"
              @open="openWork(item.id)"
          /></template>
          <template
            v-if="
              mission &&
              view === 'following' &&
              !work.s.items.some((i) => i.mission_id === mission?.id)
            "
            ><div class="section-label">{{ tr('我在跟进') }}<span class="small-count">1</span></div>
            <FollowUpCard
              @pause="open('pause')"
              @resume="act(() => shop.control('resume'))"
              @receipt="open('receipt')"
              @mission="openTask()"
              @check="act(() => shop.requestCheck())"
          /></template>
          <ForecastPanel
            v-if="s.storeId && stock?.sku_id && view !== 'journal'"
            :key="s.storeId + ':' + stock.sku_id + ':' + s.session?.principal_id"
            :store-id="s.storeId"
            :sku-id="stock.sku_id"
            :state-version="s.dashboard?.state.state_version"
            :can-manage="hasRole('operator')"
          />

          <template v-if="work.s.available && view === 'journal'"
            ><WorkCard
              v-for="item in work.s.items"
              :key="item.id"
              :item="item"
              @open="openWork(item.id)"
            /><button v-if="work.s.cursor" class="text-link" @click="work.list(true)">
              {{ tr('查看更早事项') }}
            </button></template
          >
          <template v-if="view === 'journal'"
            ><div class="view-toggle">
              <button
                :class="{ active: recordFilter === 'business' }"
                @click="recordFilter = 'business'"
              >
                {{ tr('经营变化') }}</button
              ><button
                :class="{ active: recordFilter === 'decisions' }"
                @click="recordFilter = 'decisions'"
              >
                {{ tr('我的决定') }}</button
              ><button
                :class="{ active: recordFilter === 'ledger' }"
                @click="recordFilter = 'ledger'"
              >
                {{ tr('经营账本') }}
              </button>
            </div>
            <section class="summary-card glass">
              <template v-if="recordFilter === 'ledger'"
                ><div v-for="e in s.ledger" :key="e.id" class="activity-item">
                  <time>{{ tr(when(e.simulation_time)) }}</time>
                  <div>
                    <h3>
                      {{
                        tr(
                          {
                            INIT: '场景初始化',
                            PURCHASE_ACCEPTED: '采购已受理',
                            GOODS_RECEIVED: '到货已核实',
                            SALE_RECORDED: '销售已记录',
                            DEMAND_REVISED: '需求已修订',
                          }[e.effect_type],
                        )
                      }}
                    </h3>
                    <p v-if="e.changes">
                      {{
                        joinText([
                          tr('现金变化'),
                          tr(money(e.changes.cash_delta_minor)),
                          tr('· 在库变化'),
                          tr(e.changes.on_hand_delta),
                          tr('· 在途变化'),
                          tr(e.changes.in_transit_delta),
                          tr('· 待结算变化'),
                          tr(money(e.changes.receivables_delta_minor)),
                        ])
                      }}
                    </p>
                    <p v-if="e.opening_state">
                      {{ joinText([tr('初始现金'), tr(money(e.opening_state.cash_minor))]) }}
                    </p>
                  </div>
                </div>
                <p v-if="!s.ledger.length">{{ tr('暂无账本记录。') }}</p></template
              ><template v-else
                ><div v-for="e in recordItems" :key="e.id" class="activity-item">
                  <time>{{ tr(when(e.created_at)) }}</time
                  ><span class="mini-icon"><AppIcon name="clock" /></span>
                  <div>
                    <h3>{{ e.summary }}</h3>
                    <p>{{ tr(e.actor_type === 'USER' ? '用户决定' : '后台记录') }}</p>
                  </div>
                </div>
                <p v-if="!recordItems.length">{{ tr('还没有这类记录。') }}</p>
                <button
                  v-if="s.timelineCursor"
                  class="text-link"
                  @click="act(() => shop.moreTimeline())"
                >
                  {{ tr('加载更早记录') }}
                </button></template
              >
            </section></template
          >
          <details
            v-if="
              view === 'today' &&
              s.missions.some((m) => ['COMPLETED', 'CANCELLED'].includes(m.status))
            "
            class="completed-tasks"
          >
            <summary>
              {{ tr('已结束的委托')
              }}<span>{{
                tr(s.missions.filter((m) => ['COMPLETED', 'CANCELLED'].includes(m.status)).length)
              }}</span>
            </summary>
            <button
              v-for="m in s.missions.filter((m) => ['COMPLETED', 'CANCELLED'].includes(m.status))"
              :key="m.id"
              @click="openTask(m.id)"
            >
              <span
                >{{ m.objective
                }}<small>{{
                  joinText([
                    tr(m.id.slice(-8)),
                    '·',
                    tr(m.status === 'COMPLETED' ? '已完成' : '已取消'),
                  ])
                }}</small></span
              ><AppIcon name="arrow-up-right" />
            </button>
          </details>
          <div v-if="s.alerts.some((a) => a.status === 'OPEN')" class="risk-link">
            <button class="text-link" @click="open('alerts')">
              {{
                joinText([
                  tr(s.alerts.filter((a) => a.status === 'OPEN').length),
                  tr('项经营提醒，查看依据'),
                ])
              }}<AppIcon name="chevron-right" />
            </button>
          </div>
          <div class="section-label">
            {{ tr('资料与简报') }}<span class="right">{{ tr('按需查看') }}</span>
          </div>
          <div class="materials-grid">
            <button class="follow-card glass" @click="navigate('documents')">
              <span class="mini-icon"><AppIcon name="file-check-2" /></span>
              <span
                ><h3>{{ tr('文档中心') }}</h3>
                <p>{{ tr('管理原件、资料信息与历史版本') }}</p></span
              >
              <AppIcon name="chevron-right" />
            </button>
            <button class="follow-card glass" @click="open('quote')">
              <span class="mini-icon"><AppIcon name="file-spreadsheet" /></span
              ><span
                ><h3>{{ tr('整理一份供应商报价') }}</h3>
                <p>{{ tr('查看单件价、包装、起订量与来源') }}</p></span
              ><AppIcon name="chevron-right" /></button
            ><button v-if="mission" class="follow-card glass" @click="open('brief')">
              <span class="mini-icon"><AppIcon name="file-text" /></span
              ><span
                ><h3>{{ tr('本次经营简报') }}</h3>
                <p>{{ tr('已做的决定、实际结果与下一步') }}</p></span
              ><AppIcon name="chevron-right" />
            </button>
          </div>
        </section>
        <BusinessFacts
          @overview="navigate('overview')"
          @details="open('facts')"
          @mission="mission ? openTask() : (deck = true)"
        />
      </div>
    </main>
  </div>
  <nav
    v-if="!['task', 'work'].includes(view)"
    class="workspace-dock"
    :aria-label="tr('经营快捷入口')"
  >
    <button
      v-if="mission"
      class="dock-agent-entry"
      :aria-label="tr('进入任务工作区')"
      @click="openTask(undefined, 'agent')"
    >
      <span class="agent-live-dot" :class="{ 'is-running': agent.running.value }" /><span>{{
        tr(agent.active.value || agent.s.syncError ? agent.status.value : '查看任务与 Agent')
      }}</span>
    </button>
    <button :class="{ active: view === 'today' }" @click="navigate('today')">
      <AppIcon name="panels-top-left" /><span>{{ tr('今日决策') }}</span>
      <span v-if="decisionCount" class="small-count">{{ tr(decisionCount) }}</span>
    </button>
    <button :class="{ active: view === 'following' }" @click="navigate('following')">
      <AppIcon name="orbit" /><span>{{ tr('持续跟进') }}</span>
    </button>
    <button :class="{ active: view === 'journal' }" @click="navigate('journal')">
      <AppIcon name="notebook-pen" /><span>{{ tr('经营记录') }}</span>
    </button>
    <span class="dock-divider" aria-hidden="true" />
    <button
      class="dock-utility dock-overview"
      :class="{ active: view === 'overview' }"
      :aria-current="view === 'overview' ? 'page' : undefined"
      @click="navigate('overview')"
    >
      <AppIcon name="chart-no-axes-combined" /><span>{{ tr('经营概览') }}</span>
    </button>
    <button class="dock-utility" :aria-label="tr('打开联调控制')" @click="open('controls')">
      <AppIcon name="sliders-horizontal" /><span>{{ tr('联调控制') }}</span>
    </button>
  </nav>
  <nav class="mobile-nav" :aria-label="tr('移动端导航')">
    <button
      v-for="(label, id) in { today: '今日', following: '持续跟进', journal: '经营记录' }"
      :key="id"
      :class="{ active: view === id }"
      @click="navigate(id)"
    >
      <AppIcon
        :name="{ today: 'panels-top-left', following: 'orbit', journal: 'notebook-pen' }[id]"
      />{{ tr(label) }}
    </button>
  </nav>
  <div v-if="s.notice || s.busy" class="toast" role="status">
    {{ tr(s.busy || s.notice)
    }}<button v-if="!s.busy" :aria-label="tr('关闭提示')" @click="s.notice = ''">×</button>
  </div>
  <GoalDeck
    @submitted="openWork"
    :open="deck"
    @close="deck = false"
    @start="start"
    @quote="open('quote')"
  />
  <AppDialog
    :open="Boolean(dialog)"
    :title="tr(labels[dialog] || '经营空间')"
    :busy="Boolean(s.busy) || scheduleSaving"
    @close="dialog = ''"
  >
    <p v-if="modalError" class="notice amber" role="alert">{{ tr(modalError) }}</p>
    <template v-if="dialog === 'connection'"
      ><p>
        {{ tr('使用后端已配置的用户凭证。仅通过同源服务保存为HttpOnly会话，不写localStorage。') }}
      </p>
      <form @submit.prevent="connect">
        <label class="field-label" for="token">{{ tr('后端用户凭证') }}</label
        ><input id="token" v-model="token" class="text-field" type="password" autocomplete="off" />
        <div class="modal-actions">
          <button class="primary" :disabled="!token || Boolean(s.busy)">{{ tr('连接') }}</button>
        </div>
      </form></template
    >
    <template v-else-if="dialog === 'approval' && approval"
      ><p>
        {{
          tr(
            approval.quantity
              ? '确认后只提交这一笔，后续追加仍需再次确认。'
              : '本轮保留现金，不创建采购。新情况出现后再检查；已有订单保持。',
          )
        }}
      </p>
      <div class="detail-rows">
        <div class="detail-row">
          <span>{{ tr('商品 / 供应商') }}</span
          ><b>{{
            joinText([product?.name, '/', approval.plan.input_snapshot.offer.supplier_id])
          }}</b>
        </div>
        <template v-if="approval.quantity"
          ><div class="detail-row">
            <span>{{ tr('数量与单价') }}</span
            ><b>{{
              joinText([
                tr(approval.quantity),
                tr('件 ×'),
                tr(money(approval.plan.proposed_purchase?.unit_price_minor)),
              ])
            }}</b>
          </div>
          <div class="detail-row">
            <span>{{ tr('本次支出') }}</span
            ><b>{{ tr(money(approval.plan.proposed_purchase?.total_minor)) }}</b>
          </div>
          <div class="detail-row">
            <span>{{ tr('预计到货') }}</span
            ><b>{{ tr(when(approval.plan.proposed_purchase?.expected_arrival_at)) }}</b>
          </div></template
        >
        <div class="detail-row">
          <span>{{ tr('现金变化') }}</span
          ><b>{{
            joinText([
              tr(money(approval.plan.input_snapshot.state.available_cash_minor)),
              '→',
              tr(
                money(
                  approval.plan.candidates.find((c) => c.quantity === approval!.quantity)
                    ?.cash_after_minor,
                ),
              ),
            ])
          }}</b>
        </div>
        <div class="detail-row">
          <span>{{ tr('预计剩余缺货') }}</span
          ><b>{{
            joinText([
              tr(
                approval.plan.candidates.find((c) => c.quantity === approval!.quantity)
                  ?.shortage_qty,
              ),
              tr('件'),
            ])
          }}</b>
        </div>
      </div>
      <p class="notice">
        {{
          tr(
            approval.quantity
              ? '采购受理后先计入在途，到货后才增加在库。'
              : '当前条件不变时，不会因为同一建议反复发起采购。',
          )
        }}
      </p>
      <p class="source-note">
        {{ tr('确认绑定这一份方案及当前依据。新情况出现时，需要重新核对。') }}
      </p>
      <div class="modal-actions">
        <button class="secondary" :disabled="Boolean(s.busy)" @click="dialog = ''">
          {{ tr('返回修改') }}</button
        ><button class="primary" :disabled="Boolean(s.busy) || Boolean(s.pending)" @click="submit">
          {{
            tr(
              approval.quantity
                ? `确认采购 ${approval.quantity} 件 · ${money(approval.plan.proposed_purchase?.total_minor)}`
                : '记下这次取舍',
            )
          }}
        </button>
      </div></template
    >
    <template v-else-if="dialog === 'compare' && plan"
      ><p>{{ tr('先满足最低现金约束，再比较缺货和采购量。所有数值来自这份后端方案。') }}</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{{ tr('数量') }}</th>
              <th>{{ tr('支出') }}</th>
              <th>{{ tr('剩余现金') }}</th>
              <th>{{ tr('预计缺货') }}</th>
              <th>{{ tr('约束') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in plan.candidates" :key="c.id">
              <td>{{ joinText([tr(c.quantity), tr('件')]) }}</td>
              <td>{{ tr(money(c.spend_minor)) }}</td>
              <td>{{ tr(money(c.cash_after_minor)) }}</td>
              <td>{{ joinText([tr(c.shortage_qty), tr('件')]) }}</td>
              <td>
                {{
                  tr(
                    c.rejection_reasons.length
                      ? c.rejection_reasons.map(reasonLabel).join('、')
                      : '可行',
                  )
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div></template
    >
    <template v-else-if="dialog === 'evidence' && plan"
      ><h3>{{ joinText([product?.name, tr('· 当前选择'), tr(s.selected), tr('件')]) }}</h3>
      <div class="detail-row">
        <span>{{ tr('剩余需求假设') }}</span
        ><b>{{ joinText([tr(plan.input_snapshot.forecast.remaining_demand), tr('件')]) }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('周期内可到的在途') }}</span
        ><b>{{ joinText([tr(plan.input_snapshot.eligible_inbound_qty), tr('件')]) }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('需求周期') }}</span
        ><b>{{
          joinText([
            tr(when(plan.input_snapshot.forecast.horizon_start)),
            tr('至'),
            tr(when(plan.input_snapshot.forecast.horizon_end)),
          ])
        }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('最低保留现金') }}</span
        ><b>{{ tr(money(plan.input_snapshot.policy.cash_floor_minor)) }}</b>
      </div>
      <p>
        {{
          joinText([
            tr('需求来源：'),
            tr(
              plan.input_snapshot.forecast.source === 'fixed'
                ? '固定合成场景'
                : plan.input_snapshot.forecast.source,
            ),
            '。',
            tr(plan.input_snapshot.forecast.assumptions.join('；')),
          ])
        }}
      </p>
      <details>
        <summary>{{ tr('可追溯依据') }}</summary>
        <p>
          {{
            joinText([
              tr('方案版本'),
              tr(plan.plan_version),
              tr('· 状态版本'),
              tr(plan.state_version),
              tr('· 有效至'),
              tr(when(plan.expires_at)),
            ])
          }}
        </p>
        <code class="long-id">{{ plan.proposal_hash }}</code>
      </details></template
    >
    <template v-else-if="dialog === 'receipt'"
      ><p v-if="!receiptActions.length">{{ tr('尚无已记录采购。') }}</p>
      <section v-for="a in receiptActions" :key="a.id" class="receipt">
        <h3>
          {{
            joinText([
              tr(a.quantity),
              tr('件 ·'),
              tr(money(a.amount_minor)),
              '·',
              tr(actionLabel(a.status)),
            ])
          }}
        </h3>
        <div class="detail-row">
          <span>{{ tr('采购编号') }}</span
          ><b>{{ tr(a.external_order_id || a.id) }}</b>
        </div>
        <div class="detail-row">
          <span>{{ tr('提交记录') }}</span
          ><b>{{ tr(when(a.created_at)) }}</b>
        </div>
        <div class="detail-row">
          <span>{{ tr('预计到货') }}</span
          ><b>{{ tr(when(a.purchase_snapshot.expected_arrival_at)) }}</b>
        </div>
        <div class="detail-row">
          <span>{{ tr('到货进度') }}</span
          ><b>{{
            joinText([
              tr(s.inbounds.find((i) => i.action_id === a.id)?.received_quantity || 0),
              '/',
              tr(a.quantity),
              tr('件已到货'),
            ])
          }}</b>
        </div>
        <p v-if="a.last_error" class="notice amber">{{ tr(a.last_error) }}</p>
      </section>
      <p class="notice">{{ tr('采购已受理不等于到货。进度以回执与实际到货记录为准。') }}</p>
      <button class="secondary" @click="act(() => shop.refresh(true))">
        {{ tr('查询原动作') }}
      </button></template
    >
    <template v-else-if="dialog === 'mission' && mission"
      ><h3>{{ joinText([product?.name, tr('· 活动备货')]) }}</h3>
      <p>{{ mission.objective }}</p>
      <div class="detail-row">
        <span>{{ tr('现金底线') }}</span
        ><b>{{ tr(money(mission.policy.cash_floor_minor)) }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('当前状态') }}</span
        ><b>{{
          tr(
            mission.status === 'ACTIVE'
              ? '进行中'
              : mission.status === 'PAUSED'
                ? '主动跟进已暂停'
                : '已结束',
          )
        }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('下次计划') }}</span
        ><b>{{ tr(when(mission.schedule.next_run_at)) }}</b>
      </div>
      <p>
        {{ tr('每笔采购单独确认，进展保存在应用内。关闭页面不会撤销委托，请以检查记录为准。') }}
      </p>
      <button class="primary" @click="navigate('following')">
        {{ tr('查看跟进记录') }}
      </button></template
    >
    <template v-else-if="dialog === 'complete' && mission"
      ><p>
        {{
          joinText([
            tr('结束「'),
            mission.objective,
            tr('」的主动跟进。方案、决定和采购记录保留，可随时回看。'),
          ])
        }}
      </p>
      <p class="notice">
        {{ tr('结束委托不会取消已采购的订单，也不会退回已支出的资金；到货仍按实际事实记录。') }}
      </p>
      <p v-if="mission.current_action_id || agent.active.value" class="notice amber">
        {{ tr('请先核实未决采购或停止当前 Agent 工作，再结束委托。') }}
      </p>
      <div class="modal-actions">
        <button class="secondary" @click="dialog = ''">{{ tr('继续跟进') }}</button
        ><button
          class="primary"
          :disabled="
            Boolean(s.busy) ||
            !!mission.current_action_id ||
            agent.active.value ||
            !hasRole('approver')
          "
          @click="act(() => shop.control('complete'), true)"
        >
          {{ tr('确认结束委托') }}
        </button>
      </div></template
    >
    <template v-else-if="dialog === 'pause'"
      ><p>
        {{ tr('停止新的主动检查与采购；已提交或结果不明的动作仍需核实，已发生的到货仍记录。') }}
      </p>
      <p class="notice">{{ tr('不会取消订单，也不会退回已支出的资金。') }}</p>
      <div class="modal-actions">
        <button class="secondary" @click="dialog = ''">{{ tr('继续保持') }}</button
        ><button
          class="primary"
          :disabled="Boolean(s.busy)"
          @click="act(() => shop.control('pause'), true)"
        >
          {{ tr('确认暂停主动跟进') }}
        </button>
      </div></template
    >
    <template v-else-if="dialog === 'settings'">
      <div class="settings-intro">
        <span class="settings-symbol"><AppIcon name="sliders-horizontal" /></span>
        <p>{{ tr('让经营空间更合你的习惯。') }}</p>
      </div>
      <section class="settings-section" aria-labelledby="language-heading">
        <h3 id="language-heading">{{ tr('语言与地区') }}</h3>
        <div class="settings-group">
          <div class="settings-row">
            <div>
              <strong>{{ tr('显示语言') }}</strong>
              <p>{{ tr('立即应用到整个经营空间。') }}</p>
            </div>
            <span class="settings-value">{{ tr(locale === 'en' ? 'English' : '简体中文') }}</span>
          </div>
          <fieldset class="language-options">
            <legend class="sr-only">{{ tr('显示语言') }}</legend>
            <label
              v-for="option in [
                { id: 'zh-CN', name: '简体中文', subtitle: 'Chinese, Simplified' },
                { id: 'en', name: 'English', subtitle: '英语' },
              ]"
              :key="option.id"
              class="language-option"
              :class="{ selected: locale === option.id }"
            >
              <input
                type="radio"
                name="display-language"
                :value="option.id"
                :checked="locale === option.id"
                @change="setLocale(option.id as 'zh-CN' | 'en')"
              />
              <span
                ><strong :lang="option.id">{{ option.name }}</strong
                ><small v-if="locale !== 'en' || option.id !== 'en'">{{
                  tr(option.subtitle)
                }}</small></span
              ><span class="language-check" aria-hidden="true"
                ><AppIcon v-if="locale === option.id" name="check"
              /></span>
            </label>
          </fieldset>
        </div>
        <p class="settings-footnote">
          {{ tr('选择即保存，在此浏览器中记住你的偏好。金额保留原币种，原始资料与对话保留原文。') }}
        </p>
        <p v-if="preferenceError" class="notice" role="alert">{{ tr(preferenceError) }}</p>
      </section>
      <section class="settings-section" aria-labelledby="schedule-heading">
        <h3 id="schedule-heading">{{ tr('跟进安排') }}</h3>
        <div v-if="mission" class="settings-group">
          <div class="settings-row">
            <label for="interval"
              ><strong>{{ tr('业务检查间隔') }}</strong
              ><small>{{ tr('对当前经营委托生效') }}</small></label
            >
            <select
              id="interval"
              :aria-label="tr('业务检查间隔')"
              v-model.number="scheduleSeconds"
              :disabled="
                scheduleSaving ||
                scheduleUncertainId === mission.id ||
                Boolean(s.busy) ||
                !hasRole('operator')
              "
              @change="saveSchedule"
            >
              <option
                v-for="seconds in [
                  ...new Set([
                    5,
                    15,
                    30,
                    60,
                    300,
                    900,
                    1800,
                    3600,
                    mission.schedule.interval_seconds,
                  ]),
                ].sort((a, b) => a - b)"
                :key="seconds"
                :value="seconds"
              >
                {{
                  tr(
                    seconds < 60
                      ? `${seconds} 秒`
                      : seconds % 60
                        ? `${seconds} 秒`
                        : `${seconds / 60} 分钟`,
                  )
                }}
              </option>
            </select>
          </div>
          <div class="settings-row">
            <div>
              <strong>{{ tr('主动跟进') }}</strong>
              <p>{{ tr('每笔采购仍由你单独确认。') }}</p>
            </div>
            <button
              class="text-link"
              :disabled="scheduleSaving || mission.status !== 'ACTIVE' || !hasRole('operator')"
              @click="open('pause')"
            >
              {{ tr('暂停主动跟进') }}
            </button>
          </div>
        </div>
        <div v-else class="settings-group settings-empty">{{ tr('尚未建立经营委托。') }}</div>
        <button
          v-if="mission && scheduleUncertainId === mission.id"
          class="text-link"
          :disabled="scheduleSaving"
          @click="verifySchedule"
        >
          {{ tr('重新核对安排') }}
        </button>
        <p class="settings-footnote" role="status" aria-live="polite">
          {{
            tr(
              scheduleSaving
                ? '正在保存…'
                : scheduleNotice || '选择即保存。经营检查和 Agent 对话分别运行。',
            )
          }}
        </p>
      </section>
    </template>
    <template v-else-if="dialog === 'facts'"
      ><div class="detail-row">
        <span>{{ tr('可用现金 / 预留现金') }}</span
        ><b>{{
          joinText([
            tr(money(s.dashboard?.state.available_cash_minor)),
            '/',
            tr(money(s.dashboard?.state.reserved_cash_minor)),
          ])
        }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('在库 / 在途') }}</span
        ><b>{{
          joinText([tr(number(stock?.on_hand)), '/', tr(number(stock?.in_transit)), tr('件')])
        }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('待结算') }}</span
        ><b>{{ tr(money(s.dashboard?.state.receivables_minor)) }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('来源同步状态') }}</span
        ><b>{{ tr(s.connected ? s.dashboard?.freshness.status : '无法连接') }}</b>
      </div>
      <div class="detail-row">
        <span>{{ tr('最近同步') }}</span
        ><b>{{ tr(when(s.dashboard?.freshness.last_sync_at)) }}</b>
      </div>
      <p>
        {{
          joinText([
            tr('状态版本'),
            tr(s.dashboard?.state.state_version),
            tr('。以上为真实业务API返回的合成经营状态，待结算资金不能用于采购。'),
          ])
        }}
      </p></template
    >
    <template v-else-if="dialog === 'brief'">
      <pre class="brief-text">{{ tr(briefing()) }}</pre>
      <button class="primary" @click="downloadFile(tr('ShopSteward-经营简报.txt'), briefing())">
        {{ tr('保存简报') }}
      </button></template
    >
    <template v-else-if="dialog === 'alerts'"
      ><section
        v-for="a in s.alerts.filter((a) => a.status !== 'RESOLVED')"
        :key="a.id"
        class="receipt"
      >
        <h3>
          {{
            tr(
              {
                STOCKOUT_RISK: '预计缺货风险',
                CASH_CONSTRAINT: '现金约束',
                ACTION_EXCEPTION: '采购需要核实',
                DATA_STALE: '经营数据未更新',
              }[a.type],
            )
          }}
        </h3>
        <p>{{ a.summary }}</p>
        <p>
          {{
            joinText([
              tr('最近发现：'),
              tr(when(a.last_seen_at)),
              '·',
              tr(a.status === 'ACKNOWLEDGED' ? '已知晓，尚未解除' : '待关注'),
            ])
          }}
        </p>
        <button
          v-if="a.status === 'OPEN'"
          class="secondary"
          :disabled="Boolean(s.busy) || !hasRole('operator')"
          @click="act(() => shop.acknowledge(a.id))"
        >
          {{ tr('标记已知晓') }}
        </button>
      </section>
      <p class="source-note">
        {{ tr('标记知晓不会解除风险；解除必须有新的业务证据。') }}
      </p></template
    >
    <template v-else-if="dialog === 'controls'"
      ><p>
        {{
          tr('模拟器创建并导入新场景后，此页面自动切换到新的经营环境。历史场景与任务保留供查看。')
        }}
      </p>
      <label class="field-label" for="store">{{ tr('当前可访问的店铺') }}</label
      ><select
        id="store"
        class="text-field"
        :value="s.storeId"
        @change="act(() => shop.selectStore(($event.target as HTMLSelectElement).value), true)"
      >
        <option v-if="!s.stores.length" value="">{{ tr('尚无场景') }}</option>
        <option v-for="st in s.stores" :key="st.store_id" :value="st.store_id">
          {{
            joinText([
              tr(st.store_id === s.activeStoreId ? '当前环境' : '历史场景'),
              '·',
              tr(st.store_id.slice(-8)),
              '·',
              tr(when(st.simulation_time)),
            ])
          }}
        </option>
      </select>
      <button
        v-if="s.activeStoreId && s.storeId !== s.activeStoreId"
        class="text-link"
        @click="act(() => shop.selectStore(s.activeStoreId), true)"
      >
        {{ tr('返回当前经营环境') }}
      </button>
      <div v-if="s.session?.devTools" class="demo-actions">
        <button
          class="primary"
          :disabled="Boolean(s.busy)"
          @click="act(() => shop.createScenario(), true)"
        >
          {{ tr('创建新的 SC-01 场景') }}</button
        ><button
          class="secondary"
          :disabled="Boolean(s.busy) || !s.runs[s.storeId]"
          @click="act(() => shop.advance(), true)"
        >
          {{ tr('推进下一个经营事件') }}
        </button>
      </div>
      <p class="source-note">
        {{
          tr(
            '推进按模拟器当前状态逐步执行：到货、销售、需求修订、追加到货。只有本浏览器创建的场景有控制引用，旧场景可查看或新建一轮。',
          )
        }}
      </p>
      <button class="text-link" @click="open('connection')">
        {{ tr('更换后端用户身份') }}
      </button></template
    >
    <QuotationPanel v-else-if="dialog === 'quote'" />
    <QuantitySimulationPanel
      v-else-if="dialog === 'simulation'"
      :initial="view === 'work' ? work.s.detail?.item.result?.calculation?.request : null"
      :item-id="
        view === 'work' && work.s.detail?.item.result?.calculation
          ? work.s.detail.item.id
          : undefined
      "
      :item-version="work.s.detail?.item.version"
      @created="openWork"
    />
  </AppDialog>
</template>
