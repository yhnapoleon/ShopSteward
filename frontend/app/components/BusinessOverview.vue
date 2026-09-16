<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { api, query } from '~/utils/api'
import { money, number } from '~/utils/presentation'
import {
  cashHistory,
  matchesState,
  sameContext,
  utcDay,
  utcTime,
  salesRange,
  type ReadContext,
} from '~/utils/overview'
const emit = defineEmits<{ navigate: [view: string]; controls: [] }>()
const { s, mission } = useShop()
const overview = useOverview()
const { dashboard, summary, inbounds, ledger, error, refreshing, mixed, days, custom } = overview
const state = computed(() => dashboard.value?.state)
const selectedSku = ref('')
const stock = computed(
  () => state.value?.stocks.find((x) => x.sku_id === selectedSku.value) || state.value?.stocks[0],
)
const product = computed(() => s.catalog?.products.find((x) => x.sku_id === stock.value?.sku_id))
const floor = computed(() =>
  mission.value?.store_id === s.storeId ? mission.value.policy.cash_floor_minor : undefined,
)
const cash = computed(() => cashHistory(ledger.value, dashboard.value))
const metric = ref<'quantity' | 'amount'>('quantity')
const salePoints = computed(() =>
  (summary.value?.buckets || []).map((b) => ({
    id: b.from,
    label: utcDay(b.from).slice(5).replace('-', '/'),
    detail: `${utcDay(b.from)} · 已记录销售`,
    value: metric.value === 'quantity' ? b.recorded_quantity : b.recorded_sales_amount_minor,
  })),
)
const inboundTab = ref('pending')
const pending = computed(
  () => inbounds.value?.items.filter((i) => i.arrival_status !== 'RECEIVED') || [],
)
const received = computed(
  () => inbounds.value?.items.filter((i) => i.arrival_status === 'RECEIVED') || [],
)
const inboundRows = computed(() =>
  [...(inboundTab.value === 'pending' ? pending.value : received.value)].sort((a, b) => {
    if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1
    return (a.expected_arrival_at || 'z').localeCompare(b.expected_arrival_at || 'z')
  }),
)
const mainStatus = computed(() =>
  error.facts
    ? '连接中断 · 上次数据'
    : dashboard.value?.freshness.status === 'STALE'
      ? '资料尚未同步'
      : dashboard.value?.freshness.status === 'UNKNOWN'
        ? '同步状态未知'
        : '',
)
function sectionStatus(context?: ReadContext, failure = '') {
  if (failure) return '读取失败 · 保留上次数据'
  if (!context) return ''
  if (context.freshness.status !== 'FRESH')
    return context.freshness.status === 'STALE' ? '资料尚未同步' : '同步状态未知'
  if (dashboard.value && !matchesState(context, dashboard.value)) return '读取时点不同，请刷新核对'
  return ''
}
const salesStamp = computed(() => {
  if (!summary.value) return ''
  const last = new Date(Date.parse(summary.value.to) - 1).toISOString().slice(0, 10)
  return `${utcDay(summary.value.from).slice(5).replace('-', '/')} — ${last.slice(5).replace('-', '/')}`
})
const modal = ref('')
const details = ref<HTMLDialogElement>()
const titleId = useId()
const modalTitle = computed(
  () =>
    ({
      source: '数据与来源',
      cash: '现金余额变化',
      stock: '库存明细',
      inbounds: '采购到货明细',
      sales: '销售明细',
      range: '选择销售区间',
    })[modal.value] || '',
)
let origin: HTMLElement | null = null
const sales = ref<Schema<'SaleRecord'>[]>([])
const saleContext = shallowRef<ReadContext | null>(null)
const saleCursor = ref<string | null>(null)
const saleError = ref('')
const saleLoading = ref(false)
const saleScope = reactive({ from: '', to: '' })
let detailEpoch = 0
const dateStart = ref(''),
  dateEnd = ref(''),
  dateError = ref('')
async function open(name: string) {
  origin = document.activeElement instanceof HTMLElement ? document.activeElement : null
  modal.value = name
  if (name === 'range') {
    dateStart.value = summary.value ? utcDay(summary.value.from) : ''
    dateEnd.value = summary.value
      ? new Date(Date.parse(summary.value.to) - 1).toISOString().slice(0, 10)
      : ''
    dateError.value = ''
  }
  await nextTick()
  if (!details.value?.open) details.value?.showModal()
}
function close() {
  detailEpoch++
  saleLoading.value = false
  details.value?.close()
  modal.value = ''
  origin?.isConnected && origin.focus({ preventScroll: true })
}
function goFollowing() {
  close()
  emit('navigate', 'following')
}
function outside(e: MouseEvent) {
  if (e.target !== details.value) return
  const r = details.value.getBoundingClientRect()
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)
    close()
}
function changeRange(event: Event) {
  const select = event.target as HTMLSelectElement
  if (select.value === 'custom') {
    select.value = custom.start ? 'custom' : String(days.value)
    void open('range')
  } else setRange(Number(select.value))
}
function setRange(value: number) {
  overview.setRange(value)
}
function applyRange() {
  if (
    !dateStart.value ||
    !dateEnd.value ||
    !salesRange(state.value?.simulation_time, 7, dateStart.value, dateEnd.value)
  ) {
    dateError.value = '选择不超过90天的区间，结束日期不能晚于已同步经营日期。'
    return
  }
  overview.setRange(0, dateStart.value, dateEnd.value)
  close()
}
async function showSales(index?: number) {
  if (!summary.value) return
  const bucket = index == null ? null : summary.value.buckets[index]
  saleScope.from = bucket?.from || summary.value.from
  saleScope.to = bucket?.to || summary.value.to
  sales.value = []
  saleCursor.value = null
  saleContext.value = null
  saleError.value = ''
  await open('sales')
  void loadSales()
}
async function loadSales(more = false) {
  if (saleLoading.value) return
  const id = s.storeId,
    version = s.storeVersion,
    epoch = ++detailEpoch
  saleLoading.value = true
  saleError.value = ''
  try {
    const data = await api<Schema<'SaleList'>>(
      '/api/v1/sales' +
        query({
          store_id: id,
          from: saleScope.from,
          to: saleScope.to,
          limit: 30,
          cursor: more ? saleCursor.value : null,
        }),
    )
    if (epoch !== detailEpoch || id !== s.storeId || version !== s.storeVersion) return
    if (
      data.context.store_id !== id ||
      (more && saleContext.value && !sameContext(data.context, saleContext.value))
    )
      throw Error('经营数据已变化，请重新读取明细。')
    sales.value = more
      ? [...sales.value, ...data.items].filter(
          (item, i, all) => all.findIndex((x) => x.event_id === item.event_id) === i,
        )
      : data.items
    saleContext.value = data.context
    saleCursor.value = data.next_cursor
  } catch (e) {
    if (epoch === detailEpoch) saleError.value = (e as Error).message
  } finally {
    if (epoch === detailEpoch) saleLoading.value = false
  }
}
watch(
  () => s.storeVersion,
  () => {
    close()
    selectedSku.value = ''
    inboundTab.value = 'pending'
  },
)
watch(
  () => pending.value.length,
  (count, previous) => {
    if (previous === 0 && count > 0) inboundTab.value = 'pending'
  },
)
onUnmounted(() => {
  detailEpoch++
  details.value?.close()
})
</script>

<template>
  <section class="overview" aria-labelledby="overview-title" data-testid="business-overview">
    <header class="overview-heading">
      <div>
        <button class="overview-back" @click="emit('navigate', 'today')">
          <AppIcon name="arrow-right" />{{ tr('返回今日') }}
        </button>
        <h1 id="overview-title">{{ tr('经营概览') }}<span class="overview-title-dot" /></h1>
      </div>
      <div class="overview-meta">
        <span v-if="state" class="overview-clock">{{ tr(utcTime(state.simulation_time)) }}</span>
        <button class="overview-icon" :aria-label="tr('查看概览数据来源')" @click="open('source')">
          <AppIcon name="info" />
        </button>
        <button
          class="overview-icon"
          :aria-label="tr('刷新经营概览')"
          :disabled="refreshing || !s.storeId"
          @click="overview.refresh()"
        >
          <AppIcon name="refresh-cw" :class="{ 'overview-spinning': refreshing }" />
        </button>
      </div>
    </header>
    <div v-if="!s.storeId" class="overview-empty">
      <h2>{{ tr('还没有经营数据') }}</h2>
      <p>{{ tr('选择已有经营环境后查看。') }}</p>
      <button class="secondary" @click="emit('controls')">{{ tr('选择经营环境') }}</button>
    </div>
    <div v-else>
      <div v-if="mainStatus || (mixed && !refreshing)" class="overview-warning" role="status">
        <AppIcon name="info" /><span>{{
          tr(mainStatus || '部分数据读取时点不同，请刷新核对。')
        }}</span
        ><button @click="open('source')">{{ tr('查看详情') }}</button>
      </div>
      <div v-if="!state && !error.facts" class="overview-loading" role="status">
        {{ tr('正在读取经营现状…') }}
      </div>
      <div v-else-if="!state" class="overview-empty">
        <p>{{ tr(error.facts) }}</p>
        <button class="secondary" @click="overview.refresh()">{{ tr('重新读取') }}</button>
      </div>
      <div v-else class="overview-layout">
        <section class="overview-cash" aria-labelledby="overview-cash-title">
          <div class="overview-section-head">
            <h2 id="overview-cash-title">{{ tr('可用现金') }}</h2>
          </div>
          <div class="overview-cash-value" data-testid="overview-cash">
            {{ tr(money(state.available_cash_minor)) }}
          </div>
          <div class="overview-money-context">
            <div>
              <span>{{ tr('待结算') }}</span
              ><strong data-testid="overview-receivables">{{
                tr(money(state.receivables_minor))
              }}</strong
              ><small>{{ tr('未到账') }}</small>
            </div>
            <button
              v-if="state.reserved_cash_minor > 0"
              class="overview-reserved"
              @click="open('source')"
            >
              {{ joinText([tr('采购预留'), tr(money(state.reserved_cash_minor))])
              }}<AppIcon name="info" />
            </button>
          </div>
          <div class="overview-cash-chart-head">
            <span>{{ tr('现金余额变化') }}</span
            ><button
              class="overview-icon"
              :aria-label="tr('查看现金变化明细')"
              @click="open('cash')"
            >
              <AppIcon name="arrow-up-right" />
            </button>
          </div>
          <p
            v-if="sectionStatus(ledger?.context, error.ledger)"
            class="overview-inline-warning"
            role="status"
          >
            {{ tr(sectionStatus(ledger?.context, error.ledger))
            }}<button @click="overview.refresh()">{{ tr('重试') }}</button>
          </p>
          <ClientOnly v-if="cash.length > 1"
            ><LazyOverviewChart
              kind="cash"
              :points="cash"
              :floor="state.reserved_cash_minor === 0 ? floor : undefined"
              :label="tr('按经营事件顺序的现金余额')"
              @select="open('cash')"
          /></ClientOnly>
          <div v-else-if="cash.length === 1" class="overview-chart-empty overview-cash-initial">
            <span>{{ tr('尚无现金变更') }}</span>
          </div>
          <div v-else class="overview-chart-empty">
            <span>{{ tr(refreshing ? '正在核对现金记录…' : '暂不能展示完整现金变化') }}</span
            ><button v-if="!refreshing" @click="open('cash')">{{ tr('查看记录') }}</button>
          </div>
          <div v-if="floor != null" class="overview-floor">
            <span>{{ tr('当前委托底线') }}</span
            ><b>{{ tr(money(floor)) }}</b>
          </div>
        </section>

        <section
          class="overview-sales"
          aria-labelledby="overview-sales-title"
          :aria-busy="refreshing"
        >
          <div class="overview-section-head">
            <h2 id="overview-sales-title">{{ tr('销售') }}</h2>
            <div class="overview-chart-controls">
              <div
                class="overview-segment"
                :data-active="metric === 'quantity' ? 0 : 1"
                role="group"
                :aria-label="tr('销售图表指标')"
              >
                <button :aria-pressed="metric === 'quantity'" @click="metric = 'quantity'">
                  {{ tr('销量') }}</button
                ><button :aria-pressed="metric === 'amount'" @click="metric = 'amount'">
                  {{ tr('金额') }}
                </button>
              </div>
              <select
                class="overview-range"
                :aria-label="tr('销售时间范围')"
                :value="custom.start ? 'custom' : String(days)"
                @change="changeRange"
              >
                <option value="7">{{ tr('近7日') }}</option>
                <option value="30">{{ tr('近30日') }}</option>
                <option value="custom">{{ tr('自定义') }}</option>
              </select>
            </div>
          </div>
          <div class="overview-sales-numbers">
            <strong data-testid="overview-sales-quantity"
              >{{ number(summary?.recorded_quantity)
              }}<small v-if="summary">{{ tr('件') }}</small></strong
            ><span data-testid="overview-sales-amount">{{
              money(summary?.recorded_sales_amount_minor)
            }}</span
            ><span class="overview-recorded"
              >{{ tr('已记录')
              }}<button
                class="overview-info-inline"
                :aria-label="tr('查看销售统计口径')"
                @click="open('source')"
              >
                <AppIcon name="info" /></button
            ></span>
          </div>
          <p
            v-if="sectionStatus(summary?.context, error.sales)"
            class="overview-inline-warning"
            role="status"
          >
            {{ sectionStatus(summary?.context, error.sales)
            }}<button @click="overview.refresh()">{{ tr('重试') }}</button>
          </p>
          <div class="overview-sale-plot">
            <ClientOnly v-if="summary"
              ><LazyOverviewChart
                kind="sales"
                :points="salePoints"
                :monetary="metric === 'amount'"
                :label="tr(`已记录销售，${salesStamp}，UTC日桶`)"
                @select="showSales"
            /></ClientOnly>
            <div v-else class="overview-chart-empty" role="status">
              {{ tr(error.sales ? '暂未取得销售数据' : '正在读取销售…') }}
            </div>
            <span v-if="summary?.record_count === 0" class="overview-no-sales">{{
              tr('本区间无已记录销售')
            }}</span>
          </div>
          <div class="overview-chart-footer">
            <span>{{ tr(salesStamp) }} <span v-if="summary">· UTC</span></span
            ><button :disabled="!summary" @click="showSales()">
              {{ tr('销售明细') }}<AppIcon name="arrow-up-right" />
            </button>
          </div>
        </section>

        <section class="overview-stock" aria-labelledby="overview-stock-title">
          <div class="overview-section-head">
            <h2 id="overview-stock-title">{{ tr('库存') }}</h2>
            <select
              v-if="state.stocks.length > 1"
              v-model="selectedSku"
              :aria-label="tr('库存商品')"
            >
              <option v-for="item in state.stocks" :key="item.sku_id" :value="item.sku_id">
                {{ item.sku_id }}
              </option></select
            ><span v-else class="overview-product">{{
              product?.name || stock?.sku_id || tr('暂无商品')
            }}</span>
          </div>
          <div v-if="stock" class="overview-stock-numbers">
            <div>
              <b data-testid="overview-stock">{{ tr(number(stock.on_hand)) }}</b
              ><span>{{ tr('件 · 在库') }}</span>
            </div>
            <div>
              <b data-testid="overview-transit">{{ tr(number(stock.in_transit)) }}</b
              ><span>{{ tr('件 · 在途') }}</span>
            </div>
          </div>
          <div
            v-if="stock"
            class="overview-stock-bar"
            :class="{ 'overview-stock-bar--empty': stock.on_hand + stock.in_transit === 0 }"
            aria-hidden="true"
          >
            <span
              v-show="stock.on_hand > 0"
              class="overview-onhand"
              :style="{ flex: `${stock.on_hand} 1 0px` }"
            /><span
              v-show="stock.in_transit > 0"
              class="overview-intransit"
              :style="{ flex: `${stock.in_transit} 1 0px` }"
            />
          </div>
          <div class="overview-stock-footer">
            <span v-if="stock?.in_transit">{{ tr('在途尚未入库') }}</span
            ><span v-else>{{ tr('暂无采购在途') }}</span
            ><button @click="open('stock')">
              {{ tr('库存明细') }}<AppIcon name="arrow-up-right" />
            </button>
          </div>
        </section>

        <section class="overview-inbounds" aria-labelledby="overview-inbounds-title">
          <div class="overview-section-head">
            <h2 id="overview-inbounds-title">{{ tr('采购到货') }}</h2>
            <button class="overview-link" @click="open('inbounds')">
              {{ tr('全部') }}<AppIcon name="arrow-up-right" />
            </button>
          </div>
          <div class="overview-order-tabs" role="group" :aria-label="tr('到货状态')">
            <button :aria-pressed="inboundTab === 'pending'" @click="inboundTab = 'pending'">
              {{ tr('待到货')
              }}<span v-if="inbounds?.complete">{{ tr(pending.length) }}</span></button
            ><button :aria-pressed="inboundTab === 'received'" @click="inboundTab = 'received'">
              {{ tr('已收完') }}<span v-if="inbounds?.complete">{{ tr(received.length) }}</span>
            </button>
          </div>
          <p
            v-if="sectionStatus(inbounds?.context, error.inbounds)"
            class="overview-inline-warning"
            role="status"
          >
            {{ tr(sectionStatus(inbounds?.context, error.inbounds)) }}
          </p>
          <p v-if="inbounds && !inbounds.complete" class="overview-inline-warning">
            {{ tr('当前仅显示已加载记录，未统计总数。') }}
          </p>
          <button
            v-for="item in inboundRows.slice(0, 2)"
            :key="item.action_id + item.sku_id"
            class="overview-order"
            @click="open('inbounds')"
          >
            <span
              class="overview-order-symbol"
              :class="{
                'overview-order-symbol--done': item.arrival_status === 'RECEIVED',
                'overview-order-symbol--late': item.is_overdue,
              }"
              ><AppIcon :name="item.arrival_status === 'RECEIVED' ? 'check' : 'truck'"
            /></span>
            <span class="overview-order-number"
              ><strong>{{ tr(item.remaining_quantity || item.ordered_quantity) }}</strong
              ><small>{{ tr('件') }}</small></span
            >
            <span class="overview-order-state"
              >{{
                tr(
                  item.arrival_status === 'RECEIVED'
                    ? '已收完'
                    : item.arrival_status === 'PARTIALLY_RECEIVED'
                      ? `已收 ${item.received_quantity}/${item.ordered_quantity}`
                      : '待到货',
                )
              }}<b v-if="item.is_overdue">{{ tr('已超过预计到货时点') }}</b></span
            >
            <span v-if="item.arrival_status !== 'RECEIVED'" class="overview-order-date"
              >{{ tr(item.expected_arrival_at ? utcTime(item.expected_arrival_at) : '到货时间未知')
              }}<small v-if="item.expected_arrival_at">{{ tr('预计') }}</small></span
            ><AppIcon name="chevron-right" />
          </button>
          <div v-if="!inboundRows.length" class="overview-orders-empty">
            <AppIcon :name="inbounds ? 'check' : 'clock'" /><span>{{
              tr(
                !inbounds
                  ? error.inbounds
                    ? '暂未取得到货记录'
                    : '正在读取到货…'
                  : inboundTab === 'pending'
                    ? '暂无待到货采购'
                    : '暂无已收完采购',
              )
            }}</span>
          </div>
          <button v-if="inboundRows.length > 2" class="overview-more" @click="open('inbounds')">
            {{ joinText([tr('查看其余'), tr(inboundRows.length - 2), tr('条')])
            }}<AppIcon name="arrow-up-right" />
          </button>
        </section>
      </div>
    </div>

    <dialog
      ref="details"
      class="overview-dialog"
      :aria-labelledby="titleId"
      @cancel.prevent="close"
      @click="outside"
    >
      <header class="modal-head">
        <h2 :id="titleId">{{ tr(modalTitle) }}</h2>
        <button class="icon-btn" :aria-label="tr('关闭概览详情')" @click="close">
          <AppIcon name="x" />
        </button>
      </header>
      <div class="modal-body">
        <template v-if="modal === 'source'">
          <p>{{ tr('当前为合成经营环境。正常数据按区域读取；不同请求不构成同一原子快照。') }}</p>
          <div class="overview-source-list">
            <div>
              <span>{{ tr('经营时点') }}</span
              ><b>{{ tr(utcTime(state?.simulation_time)) }}</b>
            </div>
            <div>
              <span>{{ tr('最近成功同步') }}</span
              ><b>{{ tr(utcTime(dashboard?.freshness.last_sync_at)) }}</b>
            </div>
            <div>
              <span>{{ tr('当前现金余额') }}</span
              ><b>{{ tr(money(state?.cash_minor)) }}</b>
            </div>
            <div>
              <span>{{ tr('采购预留') }}</span
              ><b>{{ tr(money(state?.reserved_cash_minor)) }}</b>
            </div>
            <div>
              <span>{{ tr('可用现金') }}</span
              ><b>{{ tr(money(state?.available_cash_minor)) }}</b>
            </div>
          </div>
          <p>
            {{
              tr(
                '可用现金＝现金余额－采购预留。待结算尚未到账，不计入可用现金。底线来自当前委托，未取得政策时不显示默认底线。',
              )
            }}
          </p>
          <h3>{{ tr('读取状态') }}</h3>
          <div class="overview-source-list">
            <div>
              <span>{{ joinText([tr('经营现状 · v'), tr(state?.state_version ?? '—')]) }}</span
              ><b>{{ tr(error.facts || dashboard?.freshness.status || '未取得') }}</b>
            </div>
            <div
              v-for="(resource, name) in { 销售: summary, 到货: inbounds, 流水: ledger }"
              :key="name"
            >
              <span>{{
                joinText([tr(name), '· v', tr(resource?.context.state_version ?? '—')])
              }}</span
              ><b>{{
                tr(
                  resource
                    ? `${resource.context.freshness.status} · ${utcTime(resource.context.as_of)}`
                    : '未取得',
                )
              }}</b>
            </div>
          </div>
          <h3>{{ tr('销售口径') }}</h3>
          <p>
            {{
              tr(
                '销售金额是已记录成交金额，不是回款或利润。按模拟经营时间的 UTC 日桶统计，包含起点、不含终点；当前经营日只含已同步记录。无记录不能证明实际零销售。日期筛选只改变销售区域。',
              )
            }}
          </p>
          <p v-if="summary">
            {{
              joinText([
                tr('查询区间：'),
                summary.from,
                tr('至'),
                summary.to,
                tr('。覆盖：RECORDED_EVENTS_ONLY。共'),
                summary.record_count,
                tr('条销售事件，不等于订单数。'),
              ])
            }}
          </p>
          <p v-for="(message, key) in error" v-show="message" :key="key" class="notice amber">
            {{ tr(message) }}
          </p>
        </template>
        <template v-else-if="modal === 'cash'">
          <p>
            {{
              tr(
                '按现金变更的发生顺序查看余额，不表示等长时间。仅完整期初及流水能与当前余额核对一致时展示曲线；预留资金的完整历史不在此图中。',
              )
            }}
          </p>
          <div v-if="cash.length" class="overview-source-list">
            <div v-for="point in cash" :key="point.id">
              <span>{{ joinText([tr(point.label), '·', tr(point.detail)]) }}</span
              ><b>{{ tr(money(point.value)) }}</b>
            </div>
          </div>
          <p v-else class="notice amber">
            {{ tr(error.ledger || '暂未取得可与当前状态核对一致的完整现金记录。') }}
          </p>
          <button class="secondary" :disabled="refreshing" @click="overview.refresh()">
            {{ tr('刷新核对') }}
          </button>
        </template>
        <template v-else-if="modal === 'stock'">
          <div v-for="item in state?.stocks" :key="item.sku_id" class="overview-detail-stock">
            <h3>
              {{ s.catalog?.products.find((p) => p.sku_id === item.sku_id)?.name || item.sku_id }}
            </h3>
            <div class="overview-source-list">
              <div>
                <span>{{ tr('在库') }}</span
                ><b>{{ joinText([tr(item.on_hand), tr('件')]) }}</b>
              </div>
              <div>
                <span>{{ tr('采购在途') }}</span
                ><b>{{ joinText([tr(item.in_transit), tr('件')]) }}</b>
              </div>
              <div>
                <span>{{ tr('剩余需求假设') }}</span
                ><b>{{ joinText([tr(item.remaining_demand), tr('件')]) }}</b>
              </div>
            </div>
            <p>{{ tr('需求是当前场景假设，不是已发生销量。在途到货后才计入库存。') }}</p>
          </div>
        </template>
        <template v-else-if="modal === 'inbounds'">
          <p>
            {{ tr('采购已受理不等于到货。已收数量依据已同步到货记录；预计时间使用模拟经营时钟。') }}
          </p>
          <p v-if="error.inbounds" class="notice amber">{{ tr(error.inbounds) }}</p>
          <p v-if="inbounds && !inbounds.complete" class="notice amber">
            {{ tr('仅展示已加载记录，不代表全部采购。') }}
          </p>
          <div class="overview-table-wrap">
            <table class="overview-table">
              <thead>
                <tr>
                  <th>{{ tr('采购') }}</th>
                  <th>{{ tr('已收 / 订购') }}</th>
                  <th>{{ tr('状态') }}</th>
                  <th>{{ tr('预计到货') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in inbounds?.items" :key="item.action_id + item.sku_id">
                  <td>{{ tr(item.external_order_id || item.action_id) }}</td>
                  <td>
                    {{
                      joinText([
                        tr(item.received_quantity),
                        '/',
                        tr(item.ordered_quantity),
                        tr('件'),
                      ])
                    }}
                  </td>
                  <td>
                    {{
                      tr(
                        item.arrival_status === 'RECEIVED'
                          ? '已收完'
                          : item.arrival_status === 'PARTIALLY_RECEIVED'
                            ? '部分到货'
                            : '待到货',
                      )
                    }}<strong v-if="item.is_overdue" class="overview-late-label">{{
                      tr('已超预计时点')
                    }}</strong>
                  </td>
                  <td>{{ tr(utcTime(item.expected_arrival_at)) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="inbounds && !inbounds.items.length">{{ tr('暂无已记录采购到货。') }}</p>
          <div class="overview-dialog-actions">
            <button class="secondary" :disabled="refreshing" @click="overview.refresh()">
              {{ tr('刷新记录') }}</button
            ><button class="primary" @click="goFollowing">
              {{ tr('返回持续跟进') }}<AppIcon name="arrow-up-right" />
            </button>
          </div>
        </template>
        <template v-else-if="modal === 'sales'">
          <p>
            {{
              joinText([
                tr(utcTime(saleScope.from)),
                '—',
                tr(utcTime(saleScope.to)),
                tr('（不含终点）'),
              ])
            }}
          </p>
          <p v-if="saleError" class="notice amber" role="alert">{{ tr(saleError) }}</p>
          <p v-if="sectionStatus(saleContext || undefined)" class="notice amber">
            {{ tr(sectionStatus(saleContext || undefined)) }}
          </p>
          <div class="overview-table-wrap">
            <table class="overview-table">
              <thead>
                <tr>
                  <th>{{ tr('经营时间（UTC）') }}</th>
                  <th>{{ tr('商品') }}</th>
                  <th>{{ tr('数量') }}</th>
                  <th>{{ tr('成交金额') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in sales" :key="item.event_id">
                  <td>{{ tr(utcTime(item.simulation_time)) }}</td>
                  <td>
                    {{
                      s.catalog?.products.find((p) => p.sku_id === item.sku_id)?.name || item.sku_id
                    }}
                  </td>
                  <td>{{ tr(number(item.quantity)) }}</td>
                  <td>{{ tr(money(item.sales_amount_minor)) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!sales.length && !saleLoading">{{ tr('本区间无已取得的销售记录。') }}</p>
          <p v-if="saleLoading" role="status">{{ tr('正在读取…') }}</p>
          <div class="overview-dialog-actions">
            <button class="secondary" :disabled="saleLoading" @click="loadSales()">
              {{ tr('重新读取') }}</button
            ><button
              v-if="saleCursor"
              class="primary"
              :disabled="saleLoading"
              @click="loadSales(true)"
            >
              {{ tr('加载更多') }}
            </button>
          </div>
        </template>
        <form v-else-if="modal === 'range'" @submit.prevent="applyRange">
          <p>{{ tr('按UTC经营日期选择，最多90天。结束日计入统计。') }}</p>
          <div class="overview-date-fields">
            <label
              >{{ tr('开始日期')
              }}<input
                v-model="dateStart"
                type="date"
                required
                :max="state?.simulation_time?.slice(0, 10)" /></label
            ><label
              >{{ tr('结束日期')
              }}<input
                v-model="dateEnd"
                type="date"
                required
                :min="dateStart"
                :max="state?.simulation_time?.slice(0, 10)"
            /></label>
          </div>
          <p v-if="dateError" class="notice amber" role="alert">{{ tr(dateError) }}</p>
          <div class="overview-dialog-actions">
            <button type="button" class="secondary" @click="close">{{ tr('取消') }}</button
            ><button class="primary" type="submit">{{ tr('应用区间') }}</button>
          </div>
        </form>
      </div>
    </dialog>
  </section>
</template>
