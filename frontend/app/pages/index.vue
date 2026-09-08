<script setup lang="ts">
import type { Schema } from '~/types/models'
import { api } from '~/utils/api'
import { money, number, when, actionLabel, reasonLabel } from '~/utils/presentation'
import { downloadFile } from '~/utils/quotations'
const shop = useShop()
const { s, mission, stock, product, plan, unresolved, canDecide, hasRole } = shop
const route = useRoute(),
  router = useRouter()
const view = computed(() =>
  ['today', 'following', 'journal', 'overview', 'documents'].includes(String(route.query.view))
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
  await shop.init()
  poll = setInterval(() => void shop.pollEnvironment(), 2500)
})
onUnmounted(() => {
  if (poll) clearInterval(poll)
  if (noticeTimer) clearTimeout(noticeTimer)
})
function open(name: string) {
  modalError.value = ''
  dialog.value = name
  scheduleSeconds.value = mission.value?.schedule.interval_seconds || 30
}
function navigate(next: string) {
  dialog.value = ''
  router.push({ query: { view: next } })
  window.scrollTo({ top: 0 })
}
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
  if (mission.value) {
    navigate('today')
    return
  }
  await act(() => shop.startMission())
  navigate('today')
}
async function connect() {
  await act(async () => {
    await $fetch('/api/session', { method: 'POST', body: { token: token.value } })
    token.value = ''
    await shop.init()
  }, true)
}
async function saveSchedule() {
  if (!mission.value) return
  await act(async () => {
    await api(`/api/v1/missions/${mission.value!.id}/schedule`, 'PATCH', {
      interval_seconds: scheduleSeconds.value,
      enabled: true,
      expected_schedule_version: mission.value!.schedule.version,
    } satisfies Schema<'ScheduleUpdate'>)
    await shop.refresh(true)
  }, true)
}
const title = computed(
  () =>
    ({
      today: s.storeId ? '今天的经营安排。' : '从示例店铺开始。',
      following: '持续跟进',
      journal: '经营记录',
      overview: '经营概览',
      documents: '文档中心',
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
  settings: '跟进安排',
  controls: '联调控制 · 合成经营环境',
  facts: '当前账目与来源',
  brief: '本次经营简报',
  quote: '整理供应商报价',
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
  ].join('\n')
}
</script>
<template>
  <div class="app">
    <header class="app-header">
      <div class="brand">
        <span class="brand-mark"><AppIcon name="layers-2" /></span><span>ShopSteward</span>
      </div>
      <nav class="nav" aria-label="主导航">
        <button
          v-for="(label, id) in { today: '今日', following: '持续跟进', journal: '经营记录' }"
          :key="id"
          :class="{ active: view === id }"
          :aria-current="view === id ? 'page' : undefined"
          @click="navigate(id)"
        >
          <AppIcon
            :name="{ today: 'panels-top-left', following: 'orbit', journal: 'notebook-pen' }[id]"
          /><span>{{ label }}</span
          ><span v-if="id === 'today' && decisionCount" class="count">{{ decisionCount }}</span>
        </button>
      </nav>
      <div class="header-store">
        <button class="store-switch" @click="open('controls')">
          <span class="avatar">店</span
          ><span
            ><strong>{{
              s.storeId ? (s.storeId === s.activeStoreId ? '当前经营环境' : '历史场景') : '选择店铺'
            }}</strong
            ><small>我的经营空间</small></span
          ><AppIcon name="chevron-down" />
        </button>
      </div>
    </header>
    <main class="workspace">
      <header v-if="!['overview', 'documents'].includes(view)" class="topbar">
        <div class="breadcrumb">
          我的经营空间<AppIcon name="chevron-right" /><b>{{
            { today: '今日', following: '持续跟进', journal: '经营记录' }[view]
          }}</b>
        </div>
        <div class="mobile-header">
          <span class="brand-mark"><AppIcon name="layers-2" /></span>ShopSteward
        </div>
        <div class="top-actions">
          <button class="demo-badge" @click="open('controls')">联调控制 · 合成数据</button
          ><span class="top-clock">{{ when(s.dashboard?.state.simulation_time) }}</span
          ><button class="icon-btn" aria-label="跟进设置" @click="open('settings')">
            <AppIcon name="sliders-horizontal" />
          </button>
        </div>
      </header>
      <div v-if="!['overview', 'documents'].includes(view)" class="page-head">
        <div>
          <div class="eyebrow">{{ s.connected ? '业务接口已连接' : '经营空间' }}</div>
          <h1>{{ title }}</h1>
          <p>
            {{
              view === 'today'
                ? '需要拍板的事情固定放在这里；其余进度按需查看。'
                : view === 'following'
                  ? '看到原委托、已完成的动作和下一步。'
                  : '事实、决定与整理结果，都可以回来核对。'
            }}
          </p>
        </div>
        <button
          class="quiet-button"
          aria-label="交给我一件事"
          :disabled="s.loading"
          @click="deck = true"
        >
          <AppIcon name="plus" /><span>交给我一件事</span>
        </button>
      </div>
      <p
        v-if="s.error && !dialog && !['overview', 'documents'].includes(view)"
        class="notice amber"
        role="alert"
      >
        {{ s.error }}
        <button class="text-link" @click="act(() => shop.refresh(true))">刷新状态</button>
      </p>
      <div v-if="s.loading" class="empty-decision glass" role="status">正在读取经营数据…</div>
      <div v-else-if="!s.session?.authenticated" class="start-card glass">
        <h2>先连接后端用户身份。</h2>
        <p>使用本机开发环境提供的用户凭证。凭证不会放入浏览器本地存储。</p>
        <button class="primary" @click="open('connection')">连接后端</button>
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
      <div v-else class="content-grid">
        <section class="main-column">
          <div v-if="view === 'today'" id="decision-zone">
            <div class="section-label">
              需要你决定<span class="small-count">{{ decisionCount }}</span
              ><span class="right">每笔采购单独确认</span>
            </div>
            <article v-if="!s.storeId" class="start-card glass">
              <span class="tag">从示例店铺开始</span>
              <h2>先准备这一轮经营资料。</h2>
              <p>创建独立SC-01场景，或选择当前身份可以查看的已有店铺。不重置旧数据。</p>
              <button
                class="primary"
                :disabled="!s.session.devTools || Boolean(s.busy)"
                @click="act(() => shop.createScenario())"
              >
                创建示例店铺
              </button>
              <p class="channel-note">创建场景不会产生采购。没有开发权限时请由管理员准备。</p>
            </article>
            <article v-else-if="issue" class="attention-card glass">
              <span class="tag amber">需要处理</span>
              <h2>
                {{
                  issue === 'confirmation'
                    ? s.pending?.storeId !== s.storeId
                      ? '历史场景的确认结果尚未取得'
                      : '确认结果尚未取得'
                    : issue === 'unknown'
                      ? '采购结果还没有核实'
                      : issue === 'expired'
                        ? '原方案已过期'
                        : '暂时无法确认最新经营数据'
                }}
              </h2>
              <p>
                {{
                  issue === 'confirmation'
                    ? '可能已经受理。查询会沿用原确认编号，不创建另一笔采购。'
                    : issue === 'unknown'
                      ? '后台正在核实原采购。不要用新采购代替查询，现金预留与原动作仍保留。'
                      : issue === 'expired'
                        ? '先重新检查适用条件，再核对新方案。'
                        : '保留上次结果供参考，恢复数据前不允许确认采购。'
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
                  issue === 'confirmation'
                    ? '查询原确认结果'
                    : issue === 'expired'
                      ? '重新检查'
                      : '刷新原记录'
                }}
              </button>
            </article>
            <article v-else-if="!mission" class="start-card glass">
              <span class="tag">从示例店铺开始</span>
              <h2>先把这次备货交代清楚。</h2>
              <p>查看库存与现金，比较补货安排；每笔采购由你确认，之后跟进到货和需求变化。</p>
              <div class="start-scope">
                <b>{{ product?.name }}</b
                ><span
                  >库存{{ number(stock?.on_hand) }}件 · 现金{{
                    money(s.dashboard?.state.available_cash_minor)
                  }}</span
                ><span>建议现金底线¥300 · 采购条件来自当前场景</span>
              </div>
              <button class="primary" :disabled="!hasRole('operator')" @click="deck = true">
                开始备货跟进<AppIcon name="arrow-right" />
              </button>
              <p class="channel-note">尚未建立委托，也没有采购。</p>
            </article>
            <DecisionCard
              v-else-if="canDecide"
              @confirm="prepare"
              @evidence="open('evidence')"
              @compare="open('compare')"
              @mission="open('mission')"
            />
            <div v-else class="empty-decision glass">
              <AppIcon
                :name="mission.status === 'PAUSED' ? 'pause' : working ? 'clock' : 'check-check'"
              />
              <div>
                <h2>
                  {{
                    working
                      ? '正在核实采购提交'
                      : mission.status === 'PAUSED'
                        ? '当前没有待确认采购'
                        : !plan
                          ? '后台正在准备方案'
                          : '暂时没有新的决定'
                  }}
                </h2>
                <p>
                  {{
                    working
                      ? '确认已经受理，采购结果以回执为准。'
                      : mission.status === 'PAUSED'
                        ? '主动检查已暂停；已提交的订单与事实记录保留。'
                        : plan?.status === 'REJECTED'
                          ? '本轮取舍已记下，有新情况再回到这里判断。'
                          : '请查看下方跟进记录。经营条件变化后，后台会重新评估。'
                  }}
                </p>
              </div>
            </div>
          </div>
          <template v-if="mission && view !== 'journal'"
            ><div class="section-label">我在跟进<span class="small-count">1</span></div>
            <details v-if="view === 'today' && canDecide" class="follow-disclosure glass">
              <summary>这项备货委托会怎样跟进</summary>
              <FollowUpCard
                @pause="open('pause')"
                @resume="act(() => shop.control('resume'))"
                @receipt="open('receipt')"
                @mission="open('mission')"
                @check="act(() => shop.requestCheck())"
              />
            </details>
            <FollowUpCard
              v-else
              conversation
              @pause="open('pause')"
              @resume="act(() => shop.control('resume'))"
              @receipt="open('receipt')"
              @mission="open('mission')"
              @check="act(() => shop.requestCheck())"
          /></template>
          <template v-if="view === 'journal'"
            ><div class="view-toggle">
              <button
                :class="{ active: recordFilter === 'business' }"
                @click="recordFilter = 'business'"
              >
                经营变化</button
              ><button
                :class="{ active: recordFilter === 'decisions' }"
                @click="recordFilter = 'decisions'"
              >
                我的决定</button
              ><button
                :class="{ active: recordFilter === 'ledger' }"
                @click="recordFilter = 'ledger'"
              >
                经营账本
              </button>
            </div>
            <section class="summary-card glass">
              <template v-if="recordFilter === 'ledger'"
                ><div v-for="e in s.ledger" :key="e.id" class="activity-item">
                  <time>{{ when(e.simulation_time) }}</time>
                  <div>
                    <h3>
                      {{
                        {
                          INIT: '场景初始化',
                          PURCHASE_ACCEPTED: '采购已受理',
                          GOODS_RECEIVED: '到货已核实',
                          SALE_RECORDED: '销售已记录',
                          DEMAND_REVISED: '需求已修订',
                        }[e.effect_type]
                      }}
                    </h3>
                    <p v-if="e.changes">
                      现金变化 {{ money(e.changes.cash_delta_minor) }} · 在库变化
                      {{ e.changes.on_hand_delta }} · 在途变化 {{ e.changes.in_transit_delta }} ·
                      待结算变化 {{ money(e.changes.receivables_delta_minor) }}
                    </p>
                    <p v-if="e.opening_state">初始现金 {{ money(e.opening_state.cash_minor) }}</p>
                  </div>
                </div>
                <p v-if="!s.ledger.length">暂无账本记录。</p></template
              ><template v-else
                ><div v-for="e in recordItems" :key="e.id" class="activity-item">
                  <time>{{ when(e.created_at) }}</time
                  ><span class="mini-icon"><AppIcon name="clock" /></span>
                  <div>
                    <h3>{{ e.summary }}</h3>
                    <p>{{ e.actor_type === 'USER' ? '用户决定' : '后台记录' }}</p>
                  </div>
                </div>
                <p v-if="!recordItems.length">还没有这类记录。</p>
                <button
                  v-if="s.timelineCursor"
                  class="text-link"
                  @click="act(() => shop.moreTimeline())"
                >
                  加载更早记录
                </button></template
              >
            </section></template
          >
          <div v-if="s.alerts.some((a) => a.status === 'OPEN')" class="risk-link">
            <button class="text-link" @click="open('alerts')">
              {{ s.alerts.filter((a) => a.status === 'OPEN').length }} 项经营提醒，查看依据<AppIcon
                name="chevron-right"
              />
            </button>
          </div>
          <div class="section-label">资料与简报<span class="right">按需查看</span></div>
          <div class="materials-grid">
            <button class="follow-card glass" @click="navigate('documents')">
              <span class="mini-icon"><AppIcon name="file-check-2" /></span>
              <span
                ><h3>文档中心</h3>
                <p>管理原件、资料信息与历史版本</p></span
              >
              <AppIcon name="chevron-right" />
            </button>
            <button class="follow-card glass" @click="open('quote')">
              <span class="mini-icon"><AppIcon name="file-spreadsheet" /></span
              ><span
                ><h3>整理一份供应商报价</h3>
                <p>查看单件价、包装、起订量与来源</p></span
              ><AppIcon name="chevron-right" /></button
            ><button v-if="mission" class="follow-card glass" @click="open('brief')">
              <span class="mini-icon"><AppIcon name="file-text" /></span
              ><span
                ><h3>本次经营简报</h3>
                <p>已做的决定、实际结果与下一步</p></span
              ><AppIcon name="chevron-right" />
            </button>
          </div>
        </section>
        <BusinessFacts
          @overview="navigate('overview')"
          @details="open('facts')"
          @mission="mission ? open('mission') : (deck = true)"
        />
      </div>
    </main>
  </div>
  <nav class="workspace-dock" aria-label="经营快捷入口">
    <div class="dock-status">
      <div class="agent-status">
        <div>
          <span
            class="goal-dot"
            :class="{ muted: !s.connected || mission?.status !== 'ACTIVE' }"
          />{{
            s.loading
              ? '正在连接'
              : !s.connected
                ? '连接待确认'
                : mission?.status === 'PAUSED'
                  ? '主动跟进已暂停'
                  : mission
                    ? '查看最近检查记录'
                    : '尚未建立委托'
          }}
        </div>
        <span>进展在应用内查看。</span>
      </div>
    </div>
    <button :class="{ active: view === 'today' }" @click="navigate('today')">
      <AppIcon name="panels-top-left" /><span>今日决策</span>
      <span v-if="decisionCount" class="small-count">{{ decisionCount }}</span>
    </button>
    <button :class="{ active: view === 'following' }" @click="navigate('following')">
      <AppIcon name="orbit" /><span>持续跟进</span>
    </button>
    <button :class="{ active: view === 'journal' }" @click="navigate('journal')">
      <AppIcon name="notebook-pen" /><span>经营记录</span>
    </button>
    <span class="dock-divider" aria-hidden="true" />
    <button
      class="dock-utility dock-overview"
      :class="{ active: view === 'overview' }"
      :aria-current="view === 'overview' ? 'page' : undefined"
      @click="navigate('overview')"
    >
      <AppIcon name="chart-no-axes-combined" /><span>经营概览</span>
    </button>
    <button class="dock-utility" aria-label="打开联调控制" @click="open('controls')">
      <AppIcon name="sliders-horizontal" /><span>联调控制</span>
    </button>
  </nav>
  <nav class="mobile-nav" aria-label="移动端导航">
    <button
      v-for="(label, id) in { today: '今日', following: '持续跟进', journal: '经营记录' }"
      :key="id"
      :class="{ active: view === id }"
      @click="navigate(id)"
    >
      <AppIcon
        :name="{ today: 'panels-top-left', following: 'orbit', journal: 'notebook-pen' }[id]"
      />{{ label }}
    </button>
  </nav>
  <div v-if="s.notice || s.busy" class="toast" role="status">
    {{ s.busy || s.notice
    }}<button v-if="!s.busy" aria-label="关闭提示" @click="s.notice = ''">×</button>
  </div>
  <GoalDeck :open="deck" @close="deck = false" @start="start" @quote="open('quote')" />
  <AppDialog
    :open="Boolean(dialog)"
    :title="labels[dialog] || '经营空间'"
    :busy="Boolean(s.busy)"
    @close="dialog = ''"
  >
    <p v-if="modalError" class="notice amber" role="alert">{{ modalError }}</p>
    <template v-if="dialog === 'connection'"
      ><p>使用后端已配置的用户凭证。仅通过同源服务保存为HttpOnly会话，不写localStorage。</p>
      <form @submit.prevent="connect">
        <label class="field-label" for="token">后端用户凭证</label
        ><input id="token" v-model="token" class="text-field" type="password" autocomplete="off" />
        <div class="modal-actions">
          <button class="primary" :disabled="!token || Boolean(s.busy)">连接</button>
        </div>
      </form></template
    >
    <template v-else-if="dialog === 'approval' && approval"
      ><p>
        {{
          approval.quantity
            ? '确认后只提交这一笔，后续追加仍需再次确认。'
            : '本轮保留现金，不创建采购。新情况出现后再检查；已有订单保持。'
        }}
      </p>
      <div class="detail-rows">
        <div class="detail-row">
          <span>商品 / 供应商</span
          ><b>{{ product?.name }} / {{ approval.plan.input_snapshot.offer.supplier_id }}</b>
        </div>
        <template v-if="approval.quantity"
          ><div class="detail-row">
            <span>数量与单价</span
            ><b
              >{{ approval.quantity }} 件 ×
              {{ money(approval.plan.proposed_purchase?.unit_price_minor) }}</b
            >
          </div>
          <div class="detail-row">
            <span>本次支出</span><b>{{ money(approval.plan.proposed_purchase?.total_minor) }}</b>
          </div>
          <div class="detail-row">
            <span>预计到货</span
            ><b>{{ when(approval.plan.proposed_purchase?.expected_arrival_at) }}</b>
          </div></template
        >
        <div class="detail-row">
          <span>现金变化</span
          ><b
            >{{ money(approval.plan.input_snapshot.state.available_cash_minor) }} →
            {{
              money(
                approval.plan.candidates.find((c) => c.quantity === approval!.quantity)
                  ?.cash_after_minor,
              )
            }}</b
          >
        </div>
        <div class="detail-row">
          <span>预计剩余缺货</span
          ><b
            >{{
              approval.plan.candidates.find((c) => c.quantity === approval!.quantity)?.shortage_qty
            }}
            件</b
          >
        </div>
      </div>
      <p class="notice">
        {{
          approval.quantity
            ? '采购受理后先计入在途，到货后才增加在库。'
            : '当前条件不变时，不会因为同一建议反复发起采购。'
        }}
      </p>
      <p class="source-note">确认绑定这一份方案及当前依据。新情况出现时，需要重新核对。</p>
      <div class="modal-actions">
        <button class="secondary" :disabled="Boolean(s.busy)" @click="dialog = ''">返回修改</button
        ><button class="primary" :disabled="Boolean(s.busy) || Boolean(s.pending)" @click="submit">
          {{
            approval.quantity
              ? `确认采购 ${approval.quantity} 件 · ${money(approval.plan.proposed_purchase?.total_minor)}`
              : '记下这次取舍'
          }}
        </button>
      </div></template
    >
    <template v-else-if="dialog === 'compare' && plan"
      ><p>先满足最低现金约束，再比较缺货和采购量。所有数值来自这份后端方案。</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>数量</th>
              <th>支出</th>
              <th>剩余现金</th>
              <th>预计缺货</th>
              <th>约束</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in plan.candidates" :key="c.id">
              <td>{{ c.quantity }}件</td>
              <td>{{ money(c.spend_minor) }}</td>
              <td>{{ money(c.cash_after_minor) }}</td>
              <td>{{ c.shortage_qty }}件</td>
              <td>
                {{
                  c.rejection_reasons.length
                    ? c.rejection_reasons.map(reasonLabel).join('、')
                    : '可行'
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div></template
    >
    <template v-else-if="dialog === 'evidence' && plan"
      ><h3>{{ product?.name }} · 当前选择{{ s.selected }}件</h3>
      <div class="detail-row">
        <span>剩余需求假设</span><b>{{ plan.input_snapshot.forecast.remaining_demand }}件</b>
      </div>
      <div class="detail-row">
        <span>周期内可到的在途</span><b>{{ plan.input_snapshot.eligible_inbound_qty }}件</b>
      </div>
      <div class="detail-row">
        <span>需求周期</span
        ><b
          >{{ when(plan.input_snapshot.forecast.horizon_start) }} 至
          {{ when(plan.input_snapshot.forecast.horizon_end) }}</b
        >
      </div>
      <div class="detail-row">
        <span>最低保留现金</span><b>{{ money(plan.input_snapshot.policy.cash_floor_minor) }}</b>
      </div>
      <p>
        需求来源：{{
          plan.input_snapshot.forecast.source === 'fixed'
            ? '固定合成场景'
            : plan.input_snapshot.forecast.source
        }}。{{ plan.input_snapshot.forecast.assumptions.join('；') }}
      </p>
      <details>
        <summary>可追溯依据</summary>
        <p>
          方案版本{{ plan.plan_version }} · 状态版本{{ plan.state_version }} · 有效至{{
            when(plan.expires_at)
          }}
        </p>
        <code class="long-id">{{ plan.proposal_hash }}</code>
      </details></template
    >
    <template v-else-if="dialog === 'receipt'"
      ><p v-if="!receiptActions.length">尚无已记录采购。</p>
      <section v-for="a in receiptActions" :key="a.id" class="receipt">
        <h3>{{ a.quantity }} 件 · {{ money(a.amount_minor) }} · {{ actionLabel(a.status) }}</h3>
        <div class="detail-row">
          <span>采购编号</span><b>{{ a.external_order_id || a.id }}</b>
        </div>
        <div class="detail-row">
          <span>提交记录</span><b>{{ when(a.created_at) }}</b>
        </div>
        <div class="detail-row">
          <span>预计到货</span><b>{{ when(a.purchase_snapshot.expected_arrival_at) }}</b>
        </div>
        <div class="detail-row">
          <span>到货进度</span
          ><b
            >{{ s.inbounds.find((i) => i.action_id === a.id)?.received_quantity || 0 }} /
            {{ a.quantity }} 件已到货</b
          >
        </div>
        <p v-if="a.last_error" class="notice amber">{{ a.last_error }}</p>
      </section>
      <p class="notice">采购已受理不等于到货。进度以回执与实际到货记录为准。</p>
      <button class="secondary" @click="act(() => shop.refresh(true))">查询原动作</button></template
    >
    <template v-else-if="dialog === 'mission' && mission"
      ><h3>{{ product?.name }} · 活动备货</h3>
      <p>{{ mission.objective }}</p>
      <div class="detail-row">
        <span>现金底线</span><b>{{ money(mission.policy.cash_floor_minor) }}</b>
      </div>
      <div class="detail-row">
        <span>当前状态</span
        ><b>{{
          mission.status === 'ACTIVE'
            ? '进行中'
            : mission.status === 'PAUSED'
              ? '主动跟进已暂停'
              : '已结束'
        }}</b>
      </div>
      <div class="detail-row">
        <span>下次计划</span><b>{{ when(mission.schedule.next_run_at) }}</b>
      </div>
      <p>每笔采购单独确认，进展保存在应用内。关闭页面不会撤销委托，请以检查记录为准。</p>
      <button class="primary" @click="navigate('following')">查看跟进记录</button></template
    >
    <template v-else-if="dialog === 'pause'"
      ><p>停止新的主动检查与采购；已提交或结果不明的动作仍需核实，已发生的到货仍记录。</p>
      <p class="notice">不会取消订单，也不会退回已支出的资金。</p>
      <div class="modal-actions">
        <button class="secondary" @click="dialog = ''">继续保持</button
        ><button
          class="primary"
          :disabled="Boolean(s.busy)"
          @click="act(() => shop.control('pause'), true)"
        >
          确认暂停主动跟进
        </button>
      </div></template
    >
    <template v-else-if="dialog === 'settings'"
      ><p>经营检查和Agent对话分别运行；暂停对话不等于暂停经营任务。</p>
      <template v-if="mission"
        ><label class="field-label" for="interval">业务检查间隔（5–3600秒）</label
        ><input
          id="interval"
          v-model.number="scheduleSeconds"
          class="text-field"
          type="number"
          min="5"
          max="3600"
        /><button
          class="primary"
          :disabled="Boolean(s.busy) || !hasRole('operator')"
          @click="saveSchedule"
        >
          保存检查安排</button
        ><button class="text-link" :disabled="mission.status !== 'ACTIVE'" @click="open('pause')">
          暂停主动跟进
        </button></template
      >
      <p v-else>尚未建立经营委托。</p>
      <p class="source-note">
        Agent当前{{
          s.session?.agentEnabled ? '已配置' : '未启用'
        }}。模型未启用时，确定性业务仍可独立运行。
      </p></template
    >
    <template v-else-if="dialog === 'facts'"
      ><div class="detail-row">
        <span>可用现金 / 预留现金</span
        ><b
          >{{ money(s.dashboard?.state.available_cash_minor) }} /
          {{ money(s.dashboard?.state.reserved_cash_minor) }}</b
        >
      </div>
      <div class="detail-row">
        <span>在库 / 在途</span
        ><b>{{ number(stock?.on_hand) }} / {{ number(stock?.in_transit) }}件</b>
      </div>
      <div class="detail-row">
        <span>待结算</span><b>{{ money(s.dashboard?.state.receivables_minor) }}</b>
      </div>
      <div class="detail-row">
        <span>来源同步状态</span
        ><b>{{ s.connected ? s.dashboard?.freshness.status : '无法连接' }}</b>
      </div>
      <div class="detail-row">
        <span>最近同步</span><b>{{ when(s.dashboard?.freshness.last_sync_at) }}</b>
      </div>
      <p>
        状态版本{{
          s.dashboard?.state.state_version
        }}。以上为真实业务API返回的合成经营状态，待结算资金不能用于采购。
      </p></template
    >
    <template v-else-if="dialog === 'brief'">
      <pre class="brief-text">{{ briefing() }}</pre>
      <button class="primary" @click="downloadFile('ShopSteward-经营简报.txt', briefing())">
        保存简报
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
            {
              STOCKOUT_RISK: '预计缺货风险',
              CASH_CONSTRAINT: '现金约束',
              ACTION_EXCEPTION: '采购需要核实',
              DATA_STALE: '经营数据未更新',
            }[a.type]
          }}
        </h3>
        <p>{{ a.summary }}</p>
        <p>
          最近发现：{{ when(a.last_seen_at) }} ·
          {{ a.status === 'ACKNOWLEDGED' ? '已知晓，尚未解除' : '待关注' }}
        </p>
        <button
          v-if="a.status === 'OPEN'"
          class="secondary"
          :disabled="Boolean(s.busy) || !hasRole('operator')"
          @click="act(() => shop.acknowledge(a.id))"
        >
          标记已知晓
        </button>
      </section>
      <p class="source-note">标记知晓不会解除风险；解除必须有新的业务证据。</p></template
    >
    <template v-else-if="dialog === 'controls'"
      ><p>模拟器创建并导入新场景后，此页面自动切换到新的经营环境。历史场景与任务保留供查看。</p>
      <label class="field-label" for="store">当前可访问的店铺</label
      ><select
        id="store"
        class="text-field"
        :value="s.storeId"
        @change="act(() => shop.selectStore(($event.target as HTMLSelectElement).value), true)"
      >
        <option v-if="!s.stores.length" value="">尚无场景</option>
        <option v-for="st in s.stores" :key="st.store_id" :value="st.store_id">
          {{ st.store_id === s.activeStoreId ? '当前环境' : '历史场景' }} ·
          {{ st.store_id.slice(-8) }} · {{ when(st.simulation_time) }}
        </option>
      </select>
      <button
        v-if="s.activeStoreId && s.storeId !== s.activeStoreId"
        class="text-link"
        @click="act(() => shop.selectStore(s.activeStoreId), true)"
      >
        返回当前经营环境
      </button>
      <div v-if="s.session?.devTools" class="demo-actions">
        <button
          class="primary"
          :disabled="Boolean(s.busy)"
          @click="act(() => shop.createScenario(), true)"
        >
          创建新的 SC-01 场景</button
        ><button
          class="secondary"
          :disabled="Boolean(s.busy) || !s.runs[s.storeId]"
          @click="act(() => shop.advance(), true)"
        >
          推进下一个经营事件
        </button>
      </div>
      <p class="source-note">
        推进按模拟器当前状态逐步执行：到货、销售、需求修订、追加到货。只有本浏览器创建的场景有控制引用，旧场景可查看或新建一轮。
      </p>
      <button class="text-link" @click="open('connection')">更换后端用户身份</button></template
    >
    <QuotationPanel v-else-if="dialog === 'quote'" />
  </AppDialog>
</template>
