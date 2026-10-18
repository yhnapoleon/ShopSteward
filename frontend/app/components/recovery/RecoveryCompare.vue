<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import {
  arrivalOf,
  blockedReason,
  candidateDays,
  caseProblem,
  conclusion,
  dayOf,
  named,
  priceOf,
  unbroken,
} from '~/utils/recovery'
import type { RecoveryCandidate, SupplierReview } from '~/types/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 2, "找货比价": reviewers read each supplier's documents, then the solver compares the
// quotes with waiting for the original order. The owner sees one row per supplier (its best
// quantity), picks one, and the button says exactly what will be bought.
const flow = useFlow()
const shop = useShop()
const { s } = shop
const state = computed(() => flow.flow.value)
const sourcing = computed(() => flow.sourcing.value)
const cmp = computed(() => flow.cmp.value)
const reading = computed(() => sourcing.value?.status === 'running')
const busy = computed(() => !!flow.working.value || state.value.actor === 'system')
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
/** Waiting means waiting for an original order only when one is still on the way. */
const originals = computed(() => flow.originals.value.some((i) => i.remaining_quantity > 0))
const waitName = computed(() => tr(originals.value ? '等原订单' : '这次不补'))

// Suppliers the reviewers read that offer nothing for this store, or could not be read.
const unread = computed(() =>
  (sourcing.value?.reviews || []).filter(
    (r) =>
      r.supplier_id !== flow.excluded.value &&
      (!r.card || r.card.status === 'no_offer') &&
      !optionOf(r.supplier_id),
  ),
)
const noOffer: Record<string, string> = {
  SKU_NOT_COVERED: '报价单里没有这件商品',
  STORE_NOT_SERVED: '不配送到门店所在区域',
  SUPPLY_WITHDRAWN: '已通知暂停供应',
}
const readerState = (supplierId: string) => {
  const review = sourcing.value?.reviews.find((r) => r.supplier_id === supplierId)
  if (!review) return { tone: 'reading', text: tr('正在读资料…') }
  return verdict(review)
}
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

const again = computed(() => state.value.again)
const offersExpired = computed(
  () =>
    cmp.value.options.length > 0 &&
    cmp.value.options.every((o) => o.blocked.includes('OFFER_EXPIRED')),
)
const canSource = computed(
  () => !!s.session?.sourcing && flow.directory.readable.value.length > 0 && flow.operator.value,
)
const declinedName = computed(() => name(flow.action.value?.purchase_snapshot.supplier_id))
const banner = computed(() => {
  const value = again.value
  if (!value) return ''
  if (value === 'declined') return named('{0}拒单，预留资金已释放。', [declinedName.value])
  if (value === 'withdrawn')
    return named('给{0}的订单已撤回，预留资金已释放。', [declinedName.value])
  if (value === 'failed') return tr('这笔采购没有成功，预留资金已释放。')
  if (value === 'expired') return tr('待确认的应急方案已过期。')
  if (value === 'superseded') return tr('待确认的应急方案被常规检查换掉了。')
  if (value === 'pending') return tr('还没有比价结果。')
  if (value === 'input')
    return caseProblem(flow.detail.value?.missing_inputs[0] || '', tr('比价缺少条件。'))
  return tr('比价结果已超过有效期，或经营数据已变化。')
})
const headline = computed(() => {
  if (flow.working.value === 'again' || flow.working.value === 'exclude') return tr('正在重新比价')
  if (flow.working.value === 'start') return tr('正在建立这次应急补货')
  if (reading.value) return tr('正在向 {0} 家供应商要报价', [sourcing.value?.suppliers.length || 0])
  if (state.value.actor === 'system') return tr('正在比价')
  if (again.value && ['declined', 'withdrawn', 'failed'].includes(again.value))
    return tr('找别家补上这个缺口')
  if (again.value) return tr('比价结果需要更新')
  return conclusion(cmp.value, originals.value)
})

const primary = computed<{ label: string; run: () => Promise<unknown> } | null>(() => {
  if (busy.value) return null
  const value = again.value
  if (value === 'declined' || value === 'withdrawn')
    return { label: named('不找{0}，重新比价', [declinedName.value]), run: flow.again }
  if (value) {
    if (offersExpired.value && canSource.value) return { label: tr('重新找货'), run: flow.resource }
    return { label: tr('重新比价'), run: flow.again }
  }
  if (offersExpired.value && canSource.value) return { label: tr('重新找货'), run: flow.resource }
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

type Analysis = {
  status?: string
  subtasks?: { subtask_id: string; status: string; claims?: { statement: string }[] }[]
}
const analysis = computed(() => flow.detail.value?.expert_analysis as Analysis | null)
const claims = computed(() =>
  (analysis.value?.subtasks || []).flatMap((t) => (t.claims || []).map((c) => c.statement)),
)
const analysisStatus: Record<string, string> = {
  running: '正在写',
  complete: '已完成',
  partial: '部分完成',
  failed: '未完成',
  disabled: '未启用',
  unavailable: '尚未配置',
  needs_input: '需要补充',
}
const fields: Record<string, string> = {
  unit_price_minor: '单价',
  minimum_order_quantity: '起订量',
  lead_time_days: '交期',
  valid_until: '有效期',
  status: '不供货的依据',
  pack_size: '装箱',
}
function choose(id: string) {
  pick.value = id
}
// The options form one radio group: Tab enters at the chosen row, arrow keys move the choice.
const group = ref<HTMLElement | null>(null)
const choices = computed(() => [
  ...cmp.value.options.filter((o) => o.feasible.length).map((o) => o.supplierId),
  ...(cmp.value.wait ? ['wait'] : []),
])
// Keyboard moves are not animated (selection highlights switch instantly); a pointer brings
// the short highlight transition back.
const keying = ref(false)
function move(event: KeyboardEvent) {
  const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key]
  const list = choices.value
  if (!step || !list.length) return
  event.preventDefault()
  keying.value = true
  const next = list[(list.indexOf(pick.value) + step + list.length) % list.length]!
  pick.value = next
  nextTick(() =>
    group.value
      ?.querySelector<HTMLElement>(`[data-recovery-option="${CSS.escape(next)}"]`)
      ?.focus(),
  )
}
function chooseQuantity(id: string, candidate: RecoveryCandidate) {
  pick.value = id
  quantities.value = { ...quantities.value, [id]: candidate.id }
}
</script>
<template>
  <div class="rf-stage rf-compare">
    <h3 class="rf-title" aria-live="polite">{{ unbroken(headline) }}</h3>
    <p v-if="gap && (reading || busy)" class="rf-sub">
      {{
        gap.short_from
          ? tr('缺 {0} 件 · 最早 {1} 缺货', [gap.shortfall_qty, dayOf(gap.short_from)])
          : tr('缺 {0} 件', [gap.shortfall_qty])
      }}
    </p>
    <p v-if="banner" class="notice amber rf-banner">{{ banner }}</p>

    <!-- Reviewers at work: one line per supplier, filled in as each one finishes. -->
    <ul v-if="reading" class="rf-readers" :aria-label="tr('读资料的进度')">
      <li
        v-for="supplier in sourcing!.suppliers"
        :key="supplier.supplier_id"
        :data-tone="readerState(supplier.supplier_id).tone"
      >
        <span class="rf-reader-mark" aria-hidden="true"
          ><AppIcon
            :name="
              readerState(supplier.supplier_id).tone === 'reading'
                ? 'loader-circle'
                : readerState(supplier.supplier_id).tone === 'ok'
                  ? 'check'
                  : 'x'
            "
        /></span>
        <b>{{ name(supplier.supplier_id) }}</b>
        <span>{{ readerState(supplier.supplier_id).text }}</span>
      </li>
    </ul>

    <!-- An outdated comparison is not shown: the card says why and offers one way forward. -->
    <template v-else-if="!busy && !again && (cmp.options.length || cmp.wait)">
      <div
        ref="group"
        class="rf-options"
        :class="{ 'is-keying': keying }"
        role="radiogroup"
        :aria-label="tr('补货选项')"
        @keydown="move"
        @pointerdown="keying = false"
      >
        <div
          v-for="option in cmp.options.filter((o) => o.feasible.length)"
          :key="option.supplierId"
          class="rf-option-slot"
          :class="{ 'is-picked': pick === option.supplierId }"
        >
          <button
            type="button"
            role="radio"
            class="rf-option"
            :aria-checked="pick === option.supplierId"
            :tabindex="pick === option.supplierId ? 0 : -1"
            :data-recovery-option="option.supplierId"
            @click="choose(option.supplierId)"
          >
            <span class="rf-radio" aria-hidden="true" />
            <span class="rf-option-name"
              >{{ name(option.supplierId)
              }}<span
                v-if="chosenOf(option.supplierId)?.id === recommendedId"
                class="tag rf-recommended"
                >{{ tr('推荐') }}</span
              ></span
            >
            <span class="rf-option-figures">
              <span>{{ tr('补 {0} 件', [chosenOf(option.supplierId)!.quantity]) }}</span>
              <span>{{ tr(money(chosenOf(option.supplierId)!.spend_minor)) }}</span>
              <span :class="{ 'is-short': chosenOf(option.supplierId)!.lost_qty > 0 }">{{
                tr('缺 {0} 件', [chosenOf(option.supplierId)!.lost_qty])
              }}</span>
              <span>{{
                arrivalOf(chosenOf(option.supplierId))
                  ? tr('{0} 前到', [dayOf(arrivalOf(chosenOf(option.supplierId)))])
                  : tr('7 天内到不了')
              }}</span>
            </span>
          </button>
          <!-- The chosen supplier's other quantities sit right under its row. -->
          <div
            v-if="pick === option.supplierId && option.feasible.length > 1"
            class="rf-quantities"
            role="group"
            :aria-label="named('{0}的数量', [name(option.supplierId)])"
          >
            <button
              v-for="candidate in option.feasible"
              :key="candidate.id"
              type="button"
              class="rf-chip"
              :aria-pressed="selected?.id === candidate.id"
              @click="chooseQuantity(option.supplierId, candidate)"
            >
              {{ tr('{0} 件', [candidate.quantity]) }}
            </button>
          </div>
        </div>
        <button
          v-if="cmp.wait"
          type="button"
          role="radio"
          class="rf-option"
          :aria-checked="pick === 'wait'"
          :tabindex="pick === 'wait' ? 0 : -1"
          data-recovery-option="wait"
          @click="choose('wait')"
        >
          <span class="rf-radio" aria-hidden="true" />
          <span class="rf-option-name"
            >{{ waitName
            }}<span v-if="cmp.wait.id === recommendedId" class="tag rf-recommended">{{
              tr('推荐')
            }}</span></span
          >
          <span class="rf-option-figures">
            <span>{{ tr('不补') }}</span>
            <span>{{ tr(money(0)) }}</span>
            <span :class="{ 'is-short': cmp.wait.lost_qty > 0 }">{{
              tr('缺 {0} 件', [cmp.wait.lost_qty])
            }}</span>
            <span />
          </span>
        </button>
        <div
          v-for="option in cmp.options.filter((o) => !o.feasible.length)"
          :key="option.supplierId"
          class="rf-option is-blocked"
          :data-recovery-option="option.supplierId"
        >
          <span class="rf-radio" aria-hidden="true" />
          <span class="rf-option-name">{{ name(option.supplierId) }}</span>
          <span class="rf-option-reason">{{
            option.blocked.map(blockedReason).join(tr('；'))
          }}</span>
        </div>
        <div
          v-for="review in unread"
          :key="review.supplier_id"
          class="rf-option is-blocked"
          :data-recovery-option="review.supplier_id"
        >
          <span class="rf-radio" aria-hidden="true" />
          <span class="rf-option-name">{{ name(review.supplier_id) }}</span>
          <span class="rf-option-reason">{{ verdict(review).text }}</span>
        </div>
      </div>
      <RecoveryDays
        v-if="selected"
        :days="candidateDays(selected)"
        :label="
          selected.quantity
            ? named('用{0}补 {1} 件的七天', [name(selected.supplier_id), selected.quantity])
            : tr(originals ? '等原订单的七天' : '不补货的七天')
        "
      />
    </template>

    <p v-for="text in sourcingMissing" :key="text" class="notice amber" role="status">
      {{ text }}
    </p>
    <p v-if="failure" class="notice" :class="{ amber: !quiet }" role="status">{{ failure }}</p>

    <details v-if="analysis && !busy && !again" class="rf-more">
      <summary>
        {{
          joinText(
            [
              tr('为什么这样比'),
              tr(analysisStatus[analysis.status || ''] || analysis.status || ''),
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
            <b>{{ tr(fields[citation.field] || citation.field) }}</b
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
          {{ tr('结束这次应急补货') }}
        </button></span
      ><span v-if="!primary && (reading || busy)" class="rf-quiet"
        ><AppIcon name="orbit" />{{
          tr(reading ? '正在读资料，不需要你操作' : '正在比价，不需要你操作')
        }}</span
      ><button
        v-else
        type="button"
        class="primary"
        :disabled="!primary || !flow.operator.value"
        data-recovery-next
        @click="primary?.run()"
      >
        {{ primary?.label || tr('先选一个补货选项') }}<AppIcon v-if="primary" name="arrow-right" />
      </button>
    </footer>
  </div>
</template>
