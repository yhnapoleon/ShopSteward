<script setup lang="ts">
import { joinText, locale, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import {
  arrivalOf,
  blockedReason,
  caseProblem,
  conclusion,
  dayOf,
  named,
  priceOf,
  shortfall,
  type SupplierOption,
  unbroken,
} from '~/utils/recovery'
import type { RecoveryCandidate, SupplierReview } from '~/types/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 2, "找货比价": reviewers read each supplier's documents, then the solver compares the
// quotes with waiting for the original order. The owner sees one row per supplier (its best
// quantity) in the plan card's light slot, a plate sliding to the pick; the picked supplier's
// neighbouring quantities sit under the slot, and the button says exactly what will be bought.
const flow = useFlow()
const shop = useShop()
const { s } = shop
const state = computed(() => flow.flow.value)
const sourcing = computed(() => flow.sourcing.value)
const cmp = computed(() => flow.cmp.value)
const reading = computed(() => sourcing.value?.status === 'running')
// Comparing is under way (suppliers being read, the analysis running, or a comparison of ours
// that has become slow): the choice steps aside. Adopting, waiting, ending or recording keep the
// choice in place; only the button waits, saying what it is doing.
const ANALYSING = ['again', 'exclude', 'start', 'source']
const busy = computed(
  () =>
    state.value.actor === 'system' ||
    (flow.actor.value === 'system' && ANALYSING.includes(flow.working.value)),
)
const waiting = computed(() => !!flow.working.value)
const doing: Record<string, string> = {
  adopt: '正在采用…',
  wait: '正在记录…',
  stop: '正在结束…',
  arrive: '正在登记…',
  again: '正在重新比价…',
  exclude: '正在重新比价…',
  source: '正在找货…',
}
const waitingLabel = computed(() => doing[flow.working.value] || '')
const name = (id: string | null | undefined) => supplierDisplayName(id)

// The owner's pick: a supplier (and one of its quantities) or waiting. Defaults to the
// recommendation whenever a new comparison arrives.
const pick = ref<string>('')
const quantities = ref<Record<string, string>>({})
watch(
  () => flow.proposal.value?.id,
  () => {
    const r = cmp.value.recommended
    pick.value = r
      ? r.supplier_id || 'wait'
      : cmp.value.options.find((o) => o.feasible.length)?.supplierId || 'wait'
    quantities.value = {}
  },
  { immediate: true },
)
const optionOf = (id: string) => cmp.value.options.find((o) => o.supplierId === id)
const chosenOf = (id: string): RecoveryCandidate | null => {
  const option = optionOf(id)
  if (!option) return null
  return option.feasible.find((c) => c.id === quantities.value[id]) || option.best
}
const selected = computed(() =>
  pick.value === 'wait' ? cmp.value.wait : pick.value ? chosenOf(pick.value) : null,
)
const recommendedId = computed(() => cmp.value.recommended?.id)
/** The supplier recommended, whichever of its quantities is picked. */
const recommendedSupplier = computed(() => cmp.value.recommended?.supplier_id ?? null)
/** Waiting means waiting for an original order only when the analysis counted on one. */
const originals = computed(() => flow.hasOriginals.value)
const waitName = computed(() => tr(originals.value ? '等原订单' : '这次不补'))
const feasibleOptions = computed(() => cmp.value.options.filter((o) => o.feasible.length))

/** The supplier's best quantity with one step either side: the trade-off without a long row. */
function tiersOf(option: SupplierOption) {
  const list = option.feasible
  const at = Math.max(
    0,
    list.findIndex((c) => c.id === option.best.id),
  )
  const start = Math.min(Math.max(0, at - 1), Math.max(0, list.length - 3))
  return list.slice(start, start + 3)
}
const picked = computed(() =>
  pick.value && pick.value !== 'wait' ? optionOf(pick.value) || null : null,
)
const tiers = computed(() => (picked.value ? tiersOf(picked.value) : []))
const tierIndex = computed(() =>
  Math.max(
    0,
    tiers.value.findIndex((c) => c.id === selected.value?.id),
  ),
)

// Suppliers the reviewers read that offer nothing for this store, or could not be read.
const unread = computed(() =>
  (sourcing.value?.reviews || []).filter(
    (r) =>
      !flow.isExcluded(r.supplier_id) &&
      (!r.card || r.card.status === 'no_offer') &&
      !optionOf(r.supplier_id),
  ),
)
const noOffer: Record<string, string> = {
  SKU_NOT_COVERED: '报价单里没有这件商品',
  STORE_NOT_SERVED: '不配送到门店所在区域',
  SUPPLY_WITHDRAWN: '已通知暂停供应',
}
const reviewOf = (supplierId: string) =>
  sourcing.value?.reviews.find((r) => r.supplier_id === supplierId)
function verdict(review: SupplierReview) {
  if (!review.card) return { tone: 'off', text: tr('资料没读明白，这家不参与比较') }
  if (review.card.status === 'no_offer' || !review.card.offer)
    return { tone: 'off', text: tr(noOffer[review.card.reason || ''] || '这家不能供货') }
  const offer = review.card.offer
  return {
    tone: 'ok',
    text: joinText(
      [
        tr('{0}/件', [priceOf(offer.unit_price_minor)]),
        tr('起订 {0} 件', [offer.minimum_order_quantity]),
        tr('每箱 {0} 件', [offer.pack_size]),
        offer.lead_time_days ? tr('{0} 天到', [offer.lead_time_days]) : tr('当日送达'),
      ],
      ' · ',
    ),
  }
}
const gap = computed(() => sourcing.value?.request)

/**
 * The day a quote's goods arrive, written as the confirmation dialog writes it ("9/8 到"): the
 * business clock plus the supplier's lead time when the documents give it. Without a lead time
 * only the settlement day is known, so the row says "9/9 前到".
 */
const DAY = 86_400_000
function arrivalText(c: RecoveryCandidate) {
  const settled = arrivalOf(c)
  if (!settled) return tr('7 天内到不了')
  const lead = c.supplier_id ? reviewOf(c.supplier_id)?.card?.offer?.lead_time_days : undefined
  const clock = s.dashboard?.state.simulation_time
  if (lead != null && clock)
    return tr('{0} 到', [dayOf(new Date(Date.parse(clock) + lead * DAY).toISOString())])
  return tr('{0} 前到', [dayOf(settled)])
}

const again = computed(() => state.value.again)
const offersExpired = computed(
  () =>
    cmp.value.options.length > 0 &&
    cmp.value.options.every((o) => o.blocked.includes('OFFER_EXPIRED')),
)
const canSource = computed(
  () => !!s.session?.sourcing && flow.directory.readable.value.length > 0 && flow.operator.value,
)
/** Every supplier that could still be compared was left out of this restock. */
const noOthers = computed(
  () =>
    !again.value &&
    flow.excludedIds.value.size > 0 &&
    !cmp.value.options.some((o) => o.feasible.length),
)
const declinedName = computed(() => name(flow.action.value?.purchase_snapshot.supplier_id))
const short = computed(() => shortfall(flow.action.value))
const released = computed(() =>
  tr('预留的 {0} 已退回 · 还缺 {1} 件', [
    money(flow.action.value?.amount_minor),
    flow.action.value?.quantity ?? 0,
  ]),
)
/** What happened, said about the thing it happened to; the reason or consequence below it. */
const head = computed<{ title: string; sub: string }>(() => {
  const gapLine = gap.value
    ? gap.value.short_from
      ? tr('缺 {0} 件 · 最早 {1} 缺货', [gap.value.shortfall_qty, dayOf(gap.value.short_from)])
      : tr('缺 {0} 件', [gap.value.shortfall_qty])
    : ''
  if (busy.value && (flow.working.value === 'again' || flow.working.value === 'exclude'))
    return { title: tr('正在重新比价'), sub: '' }
  if (busy.value && flow.working.value === 'start')
    return { title: tr('正在建立这次应急补货'), sub: '' }
  if (reading.value)
    return {
      title: tr('正在读 {0} 家供应商的资料', [sourcing.value?.suppliers.length || 0]),
      sub: gapLine,
    }
  if (state.value.actor === 'system') return { title: tr('正在比价'), sub: gapLine }
  const reason = flow.detail.value?.recheck_reason
  const detail = flow.againDetail.value
  switch (again.value) {
    case 'declined':
      return { title: named('{0}拒单了', [declinedName.value]), sub: released.value }
    case 'withdrawn':
      return { title: named('给{0}的订单已撤回', [declinedName.value]), sub: released.value }
    case 'failed':
      return { title: tr('这笔采购没有成功'), sub: released.value }
    case 'short':
      return short.value
        ? {
            title: named('{0}只确认了 {1} 件', [declinedName.value, short.value.accepted]),
            sub: tr('已按 {0} 件成交 · 还缺 {1} 件', [short.value.accepted, short.value.missing]),
          }
        : { title: tr('找别家补上这个缺口'), sub: '' }
    case 'rejected':
      return {
        title: tr('你没有采用这份应急方案'),
        sub: tr('结束这次应急补货后，系统才恢复每天的补货建议'),
      }
    case 'expired':
      return { title: tr('应急方案已过期'), sub: tr('重新比价后再确认') }
    case 'recheck':
      if (reason === 'PLAN_EXPIRED')
        return { title: tr('应急方案已过期'), sub: tr('重新比价后再确认') }
      return { title: tr('比价结果需要更新'), sub: detail }
    case 'stale':
      return { title: tr('比价结果需要更新'), sub: detail }
    case 'pending':
      // The reason the analysis did not run is the failure notice below; no second sentence.
      return { title: tr('还没有比价结果'), sub: '' }
    case 'input':
      return { title: tr('比价缺少条件'), sub: detail }
  }
  if (noOthers.value) return { title: tr('没有别的供应商可比'), sub: '' }
  const r = cmp.value.recommended
  const before = cmp.value.wait?.lost_qty ?? 0
  if (before && r && r.quantity > 0)
    return {
      title: named('{0}补 {1} 件最合适', [name(r.supplier_id), r.quantity]),
      sub: tr('7 天缺货 {0} → {1} 件 · 花 {2}', [before, r.lost_qty, money(r.spend_minor)]),
    }
  return { title: conclusion(cmp.value, originals.value), sub: '' }
})
/** Keeps "40 → 0 件" and every number with its unit on one line. */
const tight = (text: string) => unbroken(text).replace(/ → /g, '\u00a0→\u00a0')

const primary = computed<{ label: string; run: () => Promise<unknown> } | null>(() => {
  if (busy.value) return null
  const value = again.value
  if (value === 'declined' || value === 'withdrawn')
    return { label: named('不找{0}，重新比价', [declinedName.value]), run: flow.again }
  if (value === 'short') return { label: tr('缺的找别家补上'), run: flow.again }
  if (value) {
    if (offersExpired.value && canSource.value) return { label: tr('重新找货'), run: flow.resource }
    return { label: tr('重新比价'), run: flow.again }
  }
  if ((offersExpired.value || noOthers.value) && canSource.value)
    return { label: tr('重新找货'), run: flow.resource }
  const candidate = selected.value
  if (!candidate) return null
  if (candidate.quantity === 0)
    return { label: tr(originals.value ? '就等原订单' : '这次不补'), run: flow.wait }
  return {
    label: named('用{0}补 {1} 件', [name(candidate.supplier_id), candidate.quantity]),
    run: () => flow.adopt(candidate),
  }
})
const failure = computed(() =>
  flow.recovery.error.value
    ? caseProblem(flow.recovery.errorCode.value, flow.recovery.error.value)
    : flow.problem.value
      ? caseProblem(flow.problem.value.code, flow.problem.value.message)
      : '',
)
const quiet = computed(() =>
  ['SOURCING_MODEL_NOT_CONFIGURED', 'SUPPLIER_DOCUMENTS_REQUIRED', 'NO_SHORTFALL'].includes(
    flow.problem.value?.code || '',
  ),
)
const sourcingMissing = computed(() =>
  (sourcing.value?.missing || []).map((code) => caseProblem(code, code)),
)

// The model's explanation, folded. A Chinese page shows only Chinese statements, and supplier
// codes inside them ("B 的单价最低") read as the suppliers' names.
type Analysis = {
  status?: string
  subtasks?: { subtask_id: string; status: string; claims?: { statement: string }[] }[]
}
const analysis = computed(() => flow.detail.value?.expert_analysis as Analysis | null)
const han = /[㐀-鿿]/
const codes = computed(() => [
  ...new Set([
    ...cmp.value.options.map((o) => o.supplierId),
    ...(sourcing.value?.reviews || []).map((r) => r.supplier_id),
  ]),
])
const escapeRe = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const withNames = (text: string) =>
  codes.value.reduce(
    (out, id) =>
      out.replace(new RegExp(`(?<![A-Za-z0-9_])${escapeRe(id)}(?![A-Za-z0-9_])`, 'g'), name(id)),
    text,
  )
const claims = computed(() =>
  (analysis.value?.subtasks || [])
    .flatMap((t) => (t.claims || []).map((c) => c.statement))
    .filter((text) => locale.value === 'en' || han.test(text))
    .map(withNames),
)
const analysisStatus: Record<string, string> = {
  running: '正在写',
  partial: '只写了一部分',
  failed: '没写成',
}
const explained = computed(() => claims.value.length > 0 || analysis.value?.status === 'running')
const fields: Record<string, string> = {
  unit_price_minor: '单价',
  minimum_order_quantity: '起订量',
  lead_time_days: '交期',
  valid_until: '有效期',
  status: '不供货的依据',
  pack_size: '装箱',
}
/** A quote that already names its field ("单价 10.20 元") is not labelled again. */
const labelOf = (field: string, quote: string) => {
  const label = fields[field]
  return label && quote.includes(label) ? '' : tr(label || field)
}

// The options form one radio group: Tab enters at the chosen row, arrow keys move the choice.
// A plate slides to the chosen row on a pointer; anything done from the keyboard switches it
// instantly, and the first placement is never animated.
const group = ref<HTMLElement | null>(null)
const choices = computed(() => [
  ...feasibleOptions.value.map((o) => o.supplierId),
  ...(cmp.value.wait ? ['wait'] : []),
])
const keying = ref(false)
const plate = ref<{ y: number; h: number } | null>(null)
const plateLive = ref(false)
function place() {
  const row = group.value?.querySelector<HTMLElement>('[role="radio"][aria-checked="true"]')
  plate.value = row ? { y: row.offsetTop, h: row.offsetHeight } : null
}
watch(
  group,
  (el, _old, onCleanup) => {
    plateLive.value = false
    if (!el) return
    place()
    const observer = new ResizeObserver(() => place())
    observer.observe(el)
    const frame = requestAnimationFrame(() => (plateLive.value = true))
    onCleanup(() => {
      observer.disconnect()
      cancelAnimationFrame(frame)
    })
  },
  { flush: 'post' },
)
watch([pick, () => choices.value.join()], () => nextTick(place))
function choose(id: string, event?: MouseEvent) {
  if (event?.detail === 0) keying.value = true
  pick.value = id
}
function move(event: KeyboardEvent) {
  keying.value = true
  const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key]
  const list = choices.value
  if (!step || !list.length) return
  event.preventDefault()
  const next = list[(list.indexOf(pick.value) + step + list.length) % list.length]!
  pick.value = next
  nextTick(() =>
    group.value
      ?.querySelector<HTMLElement>(`[data-recovery-option="${CSS.escape(next)}"]`)
      ?.focus(),
  )
}
// Quantities: the same slot, sideways. A new supplier brings its own quantities without a slide.
const qtyLive = ref(false)
const qtyKeyed = ref(false)
let qtyFrame = 0
watch(
  pick,
  () => {
    qtyLive.value = false
    cancelAnimationFrame(qtyFrame)
    qtyFrame = requestAnimationFrame(() => (qtyLive.value = true))
  },
  { immediate: true },
)
onUnmounted(() => cancelAnimationFrame(qtyFrame))
function chooseQuantity(id: string, candidate: RecoveryCandidate, event?: MouseEvent) {
  qtyKeyed.value = event?.detail === 0
  pick.value = id
  quantities.value = { ...quantities.value, [id]: candidate.id }
}
</script>
<template>
  <div class="rf-stage rf-compare">
    <div class="rf-head-copy">
      <h3 class="rf-title" aria-live="polite">{{ tight(head.title) }}</h3>
      <p v-if="head.sub" class="rf-sub">{{ tight(head.sub) }}</p>
    </div>

    <!-- Goods already bought in this restock, with their own way to record the arrival. -->
    <RecoveryPurchases v-if="!reading" />

    <!-- Reviewers at work: one line per supplier, filled in as each one finishes. -->
    <ul v-if="reading" class="rf-readers" :aria-label="tr('读资料的进度')">
      <li
        v-for="supplier in sourcing!.suppliers"
        :key="supplier.supplier_id"
        :data-tone="
          reviewOf(supplier.supplier_id) ? verdict(reviewOf(supplier.supplier_id)!).tone : 'reading'
        "
      >
        <span class="rf-reader-mark" aria-hidden="true"
          ><AppIcon
            :name="
              !reviewOf(supplier.supplier_id)
                ? 'loader-circle'
                : verdict(reviewOf(supplier.supplier_id)!).tone === 'ok'
                  ? 'check'
                  : 'x'
            "
        /></span>
        <b>{{ name(supplier.supplier_id) }}</b>
        <span v-if="reviewOf(supplier.supplier_id)">{{
          verdict(reviewOf(supplier.supplier_id)!).text
        }}</span>
        <span v-else class="rf-skeleton" />
      </li>
    </ul>

    <!-- An outdated comparison is not shown: the card says why and offers one way forward. -->
    <template v-else-if="!busy && !again && (cmp.options.length || cmp.wait)">
      <div
        ref="group"
        class="rf-options"
        :class="{ 'is-live': plateLive && !keying }"
        role="radiogroup"
        :aria-label="tr('补货选项')"
        @keydown="move"
        @pointerdown="keying = false"
      >
        <span
          class="rf-plate"
          aria-hidden="true"
          :style="
            plate
              ? { transform: `translateY(${plate.y}px)`, height: plate.h + 'px' }
              : { display: 'none' }
          "
        />
        <button
          v-for="option in feasibleOptions"
          :key="option.supplierId"
          type="button"
          role="radio"
          class="rf-option"
          :aria-checked="pick === option.supplierId"
          :tabindex="pick === option.supplierId ? 0 : -1"
          :data-recovery-option="option.supplierId"
          @click="choose(option.supplierId, $event)"
        >
          <span class="rf-radio" aria-hidden="true" />
          <span class="rf-option-name"
            >{{ name(option.supplierId)
            }}<span v-if="option.supplierId === recommendedSupplier" class="tag rf-recommended">{{
              tr('推荐')
            }}</span></span
          >
          <span class="rf-option-figures">
            <span>{{ unbroken(tr('补 {0} 件', [chosenOf(option.supplierId)!.quantity])) }}</span>
            <span>{{ tr(money(chosenOf(option.supplierId)!.spend_minor)) }}</span>
            <span :class="chosenOf(option.supplierId)!.lost_qty > 0 ? 'is-short' : 'is-zero'">{{
              unbroken(tr('缺 {0} 件', [chosenOf(option.supplierId)!.lost_qty]))
            }}</span>
            <span>{{ unbroken(arrivalText(chosenOf(option.supplierId)!)) }}</span>
          </span>
        </button>
        <button
          v-if="cmp.wait"
          type="button"
          role="radio"
          class="rf-option"
          :aria-checked="pick === 'wait'"
          :tabindex="pick === 'wait' ? 0 : -1"
          data-recovery-option="wait"
          @click="choose('wait', $event)"
        >
          <span class="rf-radio" aria-hidden="true" />
          <span class="rf-option-name"
            >{{ waitName
            }}<span v-if="cmp.wait.id === recommendedId" class="tag rf-recommended">{{
              tr('推荐')
            }}</span></span
          >
          <span class="rf-option-figures">
            <span class="is-zero">{{ tr('不补') }}</span>
            <span class="is-zero">{{ tr(money(0)) }}</span>
            <span :class="cmp.wait.lost_qty > 0 ? 'is-short' : 'is-zero'">{{
              unbroken(tr('缺 {0} 件', [cmp.wait.lost_qty]))
            }}</span>
            <span />
          </span>
        </button>
      </div>
      <!-- The picked supplier's quantities: its best one with one step either side. -->
      <div v-if="picked && tiers.length > 1" :key="pick" class="rf-qty-row">
        <span class="rf-qty-label" aria-hidden="true">{{ tr('数量') }}</span
        ><span
          class="rf-seg rf-qty"
          :class="{ 'is-live': qtyLive && !qtyKeyed }"
          role="group"
          :aria-label="named('{0}的数量', [name(pick)])"
          :style="{ '--seg-count': tiers.length, '--seg-index': tierIndex }"
          @pointerdown="qtyKeyed = false"
        >
          <button
            v-for="candidate in tiers"
            :key="candidate.id"
            type="button"
            class="rf-seg-item"
            :aria-pressed="selected?.id === candidate.id"
            @click="chooseQuantity(pick, candidate, $event)"
          >
            <b>{{ unbroken(tr('{0} 件', [candidate.quantity])) }}</b
            ><small>{{
              unbroken(tr('{0} · 缺 {1}', [money(candidate.spend_minor), candidate.lost_qty]))
            }}</small
            ><span v-if="candidate.id === recommendedId" class="rf-tier-recommended">{{
              tr('推荐')
            }}</span>
          </button>
        </span>
      </div>
      <!-- Suppliers that cannot be chosen, and why; outside the choice itself. -->
      <ul
        v-if="cmp.options.some((o) => !o.feasible.length) || unread.length"
        class="rf-unavailable"
      >
        <li
          v-for="option in cmp.options.filter((o) => !o.feasible.length)"
          :key="option.supplierId"
          :data-recovery-option="option.supplierId"
        >
          <span>{{ name(option.supplierId) }}</span
          ><span>{{ option.blocked.map(blockedReason).join(tr('；')) }}</span>
        </li>
        <li
          v-for="review in unread"
          :key="review.supplier_id"
          :data-recovery-option="review.supplier_id"
        >
          <span>{{ name(review.supplier_id) }}</span
          ><span>{{ verdict(review).text }}</span>
        </li>
      </ul>
    </template>

    <p v-for="text in sourcingMissing" :key="text" class="notice amber" role="status">
      {{ text }}
    </p>
    <p v-if="failure" class="notice" :class="{ amber: !quiet }" role="status">{{ failure }}</p>

    <details v-if="analysis && explained && !busy && !again" class="rf-more">
      <summary>
        {{
          joinText(
            [
              tr('为什么这样比'),
              analysisStatus[analysis.status || '']
                ? tr(analysisStatus[analysis.status || ''])
                : '',
              claims.length ? tr('{0} 条', [claims.length]) : '',
            ].filter(Boolean),
            ' · ',
          )
        }}
      </summary>
      <p class="source-note">{{ tr('解释由模型写，金额和数量以上面的比较为准。') }}</p>
      <ul class="rf-claims">
        <li v-for="(claim, index) in claims" :key="index">{{ claim }}</li>
      </ul>
    </details>
    <details v-if="sourcing?.reviews.length && !reading && !again" class="rf-more">
      <summary>{{ tr('每家资料怎么读的') }}</summary>
      <article
        v-for="review in sourcing.reviews"
        :key="review.supplier_id"
        class="rf-reading"
        :data-sourcing-review="review.supplier_id"
      >
        <h4>{{ name(review.supplier_id) }}</h4>
        <p>{{ verdict(review).text }}</p>
        <ul v-if="review.card?.citations.length" class="rf-citations">
          <li v-for="(citation, index) in review.card.citations" :key="index">
            <b v-if="labelOf(citation.field, citation.quote)">{{
              labelOf(citation.field, citation.quote)
            }}</b
            ><q>{{ citation.quote }}</q>
          </li>
        </ul>
      </article>
    </details>

    <footer class="rf-next">
      <span class="rf-links"
        ><button
          v-if="canSource && !reading && !busy && !offersExpired && !again"
          type="button"
          class="text-link"
          @click="flow.resource()"
        >
          {{ tr('重新找货') }}</button
        ><button
          v-if="flow.operator.value && !busy"
          type="button"
          class="text-link"
          @click="flow.stop()"
        >
          {{ tr('结束这次应急补货') }}</button
        ><button
          v-if="flow.canReturnToConfirm.value && !busy"
          type="button"
          class="text-link"
          @click="flow.backToConfirm()"
        >
          {{ tr('不换了，回去确认') }}
        </button></span
      ><span v-if="!primary && (reading || busy)" class="rf-quiet"
        ><AppIcon name="orbit" />{{
          tr(reading ? '正在读资料，不需要你操作' : '正在比价，不需要你操作')
        }}</span
      ><button
        v-else
        type="button"
        class="primary"
        :disabled="!primary || !flow.operator.value || waiting"
        data-recovery-next
        @click="primary?.run()"
      >
        {{ waiting && waitingLabel ? tr(waitingLabel) : primary?.label || tr('先选一个补货选项')
        }}<AppIcon v-if="primary && !waiting" name="arrow-right" />
      </button>
    </footer>
  </div>
</template>
