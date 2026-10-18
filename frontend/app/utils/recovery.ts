import { intlLocale, t } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import type { PlanDocument, Schema } from '~/types/models'
import type { RecoveryCandidate, RecoveryCase, RecoveryProposal, Sourcing } from '~/types/recovery'

// Emergency restock (应急补货) as one flow on the work page: one Case, one progress line, the next
// step always in the same place. Everything here is derived from the recovery Case, its plan and
// its purchase order; nothing writes business data. Quantities follow the recovery solver's own
// daily settlement rule (backend planning/recovery/solver.py), so the brief and the comparison
// agree on the gap before and after the backend is asked.

const DAY = 86_400_000

/** Why an emergency restock is opened; the brief's first sentence is written from it. */
export type RecoveryReason =
  | 'manual'
  | 'late'
  | 'stockout'
  | 'cash'
  | 'infeasible'
  | 'failed'
  | 'declined'
  | 'partial'
  | 'expired'

export type RecoveryLaunch = {
  missionId: string
  reason: RecoveryReason
  /** Units a trigger already knows are short (an alert's facts), used when no projection exists. */
  gap?: number | null
  /** A supplier that declined or could not supply everything: left out of the next comparison. */
  exclude?: string | null
  at: number
}

export type StageKey = 'brief' | 'compare' | 'confirm' | 'order' | 'receive' | 'result'
export type Actor = 'you' | 'system' | 'done'
/** buy: an order the owner sends; direct: the connected supplier's system; wait: no purchase. */
export type FlowVariant = 'buy' | 'direct' | 'wait'
export type Again =
  | 'pending'
  | 'declined'
  | 'failed'
  | 'withdrawn'
  | 'expired'
  | 'stale'
  | 'superseded'
  | 'input'
export type FlowStep = { key: StageKey; label: string }

const STEPS: Record<FlowVariant, FlowStep[]> = {
  buy: [
    { key: 'brief', label: '说明情况' },
    { key: 'compare', label: '找货比价' },
    { key: 'confirm', label: '采用并确认' },
    { key: 'order', label: '发单并登记回复' },
    { key: 'receive', label: '登记到货' },
    { key: 'result', label: '结果' },
  ],
  direct: [
    { key: 'brief', label: '说明情况' },
    { key: 'compare', label: '找货比价' },
    { key: 'confirm', label: '采用并确认' },
    { key: 'order', label: '系统下单' },
    { key: 'receive', label: '等待到货' },
    { key: 'result', label: '结果' },
  ],
  wait: [
    { key: 'brief', label: '说明情况' },
    { key: 'compare', label: '找货比价' },
    { key: 'confirm', label: '决定等原订单' },
    { key: 'receive', label: '等原订单到货' },
    { key: 'result', label: '结果' },
  ],
}
/**
 * Step labels are catalog keys: translate them with t() where they are shown. Choosing to wait
 * when no original order is on the way means not restocking at all: that flow has four steps.
 */
export const flowSteps = (variant: FlowVariant, originals = true): FlowStep[] =>
  variant === 'wait' && !originals
    ? [
        { key: 'brief', label: '说明情况' },
        { key: 'compare', label: '找货比价' },
        { key: 'confirm', label: '决定这次不补' },
        { key: 'result', label: '结果' },
      ]
    : STEPS[variant]

export type FlowFacts = {
  detail: RecoveryCase | null
  /** The Case's own purchase order, read from the shop's order list. */
  action: Schema<'Action'> | null
  inbound: Schema<'InboundItem'> | null
  /** Original orders the Case's analysis counted on (the waiting variant watches them). */
  originals: Schema<'InboundItem'>[]
}
export type FlowState = {
  variant: FlowVariant
  stage: StageKey
  actor: Actor
  /** The Case is over (or its purchase fully arrived): it shrinks to one summary line. */
  ended: boolean
  /** Comparing again, and why. */
  again: Again | null
}
const TERMINAL = ['CANCELLED', 'CLOSED', 'RESOLVED']
const state = (
  variant: FlowVariant,
  stage: StageKey,
  actor: Actor,
  ended = false,
  again: Again | null = null,
): FlowState => ({ variant, stage, actor, ended, again })

/** Where the Case stands, read from the backend's facts (the Case is never marked resolved). */
export function flowState({ detail: d, action: a, inbound, originals }: FlowFacts): FlowState {
  if (!d) return state('buy', 'brief', 'you')
  const terminal = TERMINAL.includes(d.status)
  if (a) {
    const variant: FlowVariant = a.channel === 'assisted' ? 'buy' : 'direct'
    if (a.status === 'SUCCEEDED') {
      const arrived = inbound ? inbound.remaining_quantity === 0 : d.execution_status === 'RECEIVED'
      if (arrived) return state(variant, 'result', 'done', true)
      // Goods still on the way; a Case stopped by hand keeps them visible as a summary.
      return state(variant, 'receive', variant === 'buy' ? 'you' : 'system', terminal)
    }
    if (a.status === 'EXECUTING' && variant === 'buy') return state(variant, 'order', 'you')
    if (['QUEUED', 'EXECUTING', 'UNKNOWN'].includes(a.status))
      return state(variant, 'order', 'system')
    // Declined, failed, withdrawn or overtaken: nothing was bought, so compare again. The Case
    // keeps pointing at that order until another quote is adopted, so once it has been revised
    // since, the order no longer decides the stage.
    if (terminal) return state('buy', 'result', 'done', true)
    if ((d.plan_revision ?? d.current_revision) >= d.current_revision) {
      const again: Again =
        a.status === 'CANCELLED'
          ? 'withdrawn'
          : a.supplier_reply?.outcome === 'declined'
            ? 'declined'
            : 'failed'
      return state('buy', 'compare', 'you', false, again)
    }
  }
  if (terminal) return state('buy', 'result', 'done', true)
  // The owner chose to wait: the Case watches the original orders until they are in.
  if (d.status === 'MONITORING' && d.plan_status !== 'PENDING_APPROVAL') {
    const outstanding = originals.some((i) => i.remaining_quantity > 0)
    return outstanding ? state('wait', 'receive', 'system') : state('wait', 'result', 'done', true)
  }
  if (d.plan_id && d.plan_revision === d.current_revision) {
    if (d.plan_status === 'PENDING_APPROVAL') return state('buy', 'confirm', 'you')
    // A regular check replaced the pending plan, or its time ran out.
    if (d.plan_status === 'EXPIRED' || d.plan_status === 'SUPERSEDED')
      return state(
        'buy',
        'compare',
        'you',
        false,
        d.plan_status === 'EXPIRED' ? 'expired' : 'superseded',
      )
  }
  if ((d.sourcing as Sourcing | null | undefined)?.status === 'running')
    return state('buy', 'compare', 'system')
  if (d.status === 'OPTIONS_READY' && d.proposal)
    return state('buy', 'compare', 'you', false, d.stale ? 'stale' : null)
  if (d.status === 'NEEDS_INPUT' || d.status === 'BLOCKED')
    return state('buy', 'compare', 'you', false, 'input')
  if (d.status === 'RECHECK_REQUIRED') return state('buy', 'compare', 'you', false, 'stale')
  // Created or revised but never analyzed: the analysis this page started failed (its reason is
  // shown beside the card) or never ran. Analyses run inside the request, so nothing is pending.
  return state('buy', 'compare', 'you', false, 'pending')
}

/** Seven whole quantities adding up to `total`, the larger ones first. */
export function evenDays(total: number, days = 7) {
  const whole = Math.max(0, Math.round(total))
  const base = Math.floor(whole / days),
    extra = whole - base * days
  return Array.from({ length: days }, (_, i) => base + (i < extra ? 1 : 0))
}

/**
 * The backend's allocation of a daily forecast into whole units (solver.allocate_daily): floors,
 * then the remainder to the largest fractions. Null when the values cannot be allocated.
 */
export function allocateDaily(values: number[], total: number) {
  if (values.length !== 7 || values.some((v) => !Number.isFinite(v) || v < 0)) return null
  const floors = values.map((v) => Math.floor(v))
  const remainder = total - floors.reduce((n, v) => n + v, 0)
  if (remainder < 0 || remainder > 7) return null
  ;[...values.keys()]
    .sort((a, b) => values[b]! - floors[b]! - (values[a]! - floors[a]!) || a - b)
    .slice(0, remainder)
    .forEach((i) => (floors[i]! += 1))
  return floors
}

/** Daily settlements the solver accepts: the end of each business day from the shop's clock. */
export function settlements(clock: string, days = 7) {
  const start = Date.parse(clock)
  return Array.from({ length: days }, (_, i) =>
    new Date(start + (i + 1) * DAY - 1000).toISOString(),
  )
}

/** One settlement day as the day strip draws it. */
export type DayRow = { at: string; demand: number; lost: number; arriving: number }
export type Projection = {
  lost: number
  shortFrom: string | null
  endStock: number
  days: DayRow[]
}

/**
 * Stock day by day with no new purchase, as the solver settles it: an original order counts on
 * the day it is due, and one already overdue is not counted at all.
 */
export function projectWithout(
  onHand: number,
  demand: number[],
  dates: string[],
  arrivals: { quantity: number; at: string | null }[],
  clock: string,
): Projection {
  const start = Date.parse(clock)
  let stock = onHand,
    lost = 0,
    shortFrom: string | null = null
  let pending = arrivals.filter((a) => a.quantity > 0)
  const days = demand.map((qty, i) => {
    const end = Date.parse(dates[i]!)
    const due = pending.filter((a) => a.at && Date.parse(a.at) >= start && Date.parse(a.at) <= end)
    pending = pending.filter((a) => !due.includes(a))
    const arriving = due.reduce((n, a) => n + a.quantity, 0)
    const available = stock + arriving
    const served = Math.min(available, qty)
    stock = available - served
    if (qty > served) {
      lost += qty - served
      shortFrom ??= dates[i]!
    }
    return { at: dates[i]!, demand: qty, lost: qty - served, arriving }
  })
  return { lost, shortFrom, endStock: stock, days }
}

/** A candidate's seven days for the day strip; the arriving units are the new purchase. */
export const candidateDays = (c: RecoveryCandidate | null | undefined): DayRow[] =>
  (c?.daily || []).map((d) => ({
    at: d.settlement_at,
    demand: d.demand_qty,
    lost: d.lost_qty,
    arriving: d.proposed_arrivals,
  }))

export type DemandSource = 'forecast' | 'assumption' | 'daily'
export type DemandPlan = { values: number[]; source: DemandSource }

/**
 * The seven days of demand the brief starts from: the enabled daily forecast when there is one,
 * otherwise the mission's current demand assumption spread evenly over the same seven days.
 */
export function demandFrom(input: {
  forecast?: { usable_for_planning: boolean; forecast: Record<string, unknown> | null } | null
  plan?: PlanDocument | null
  remainingDemand?: number | null
}): DemandPlan {
  const doc = input.forecast?.usable_for_planning ? input.forecast.forecast : null
  const daily = (doc?.daily_predictions as { quantity: number }[] | undefined)?.map(
    (d) => d.quantity,
  )
  const predicted = doc?.predicted_quantity as number | undefined
  if (daily?.length === 7 && typeof predicted === 'number') {
    const values = allocateDaily(daily, predicted)
    if (values) return { values, source: 'forecast' }
  }
  const forecast = input.plan?.input_snapshot.forecast
  if (forecast) {
    const days = Math.max(
      1,
      Math.round((Date.parse(forecast.horizon_end) - Date.parse(forecast.horizon_start)) / DAY),
    )
    return {
      values: evenDays((forecast.remaining_demand * 7) / days),
      source: 'assumption',
    }
  }
  return { values: evenDays(input.remainingDemand || 0), source: 'assumption' }
}

/** The brief's first sentence, in the owner's language; it becomes the Case objective. */
export function objectiveFor(
  reason: RecoveryReason,
  projection: Projection | null,
  supplier?: string | null,
) {
  const name = supplier ? supplierDisplayName(supplier) : ''
  const lost = projection?.lost ?? 0
  const from = projection?.shortFrom ? dayOf(projection.shortFrom) : ''
  if (!lost)
    return named(
      reason === 'declined'
        ? '{0}拒单，找别家补上；按当前需求，7 天内暂不缺货。'
        : reason === 'partial'
          ? '{0}只能供应一部分，撤回后找别家补上；按当前需求，7 天内暂不缺货。'
          : '按当前需求，7 天内暂不缺货。',
      [name],
    )
  const template: Record<RecoveryReason, string> = {
    manual: '不补的话 {0} 起缺货，7 天共缺 {1} 件。',
    late: '原订单晚到：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
    stockout: '预计缺货：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
    cash: '现金不够按原计划补货：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
    infeasible: '常规方案没有可行的采购：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
    failed: '采购没有成功：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
    declined: '{2}拒单，找别家补上：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
    partial: '{2}只能供应一部分，撤回后找别家补上：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
    expired: '报价已过期，重新找货：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
  }
  return named(template[reason], [from, lost, name], 2)
}

export type SupplierOption = {
  supplierId: string
  /** What this supplier would do best: least shortage, then least spend (the solver's order). */
  best: RecoveryCandidate
  /** Feasible quantities from this supplier, smallest first. */
  feasible: RecoveryCandidate[]
  /** Why none of its quantities can be bought, when that is the case. */
  blocked: string[]
}
export type Comparison = {
  wait: RecoveryCandidate | null
  options: SupplierOption[]
  recommended: RecoveryCandidate | null
}
const rank = (c: RecoveryCandidate) => [c.lost_qty, c.spend_minor, c.end_stock, c.quantity]
const byRank = (a: RecoveryCandidate, b: RecoveryCandidate) => {
  const x = rank(a),
    y = rank(b)
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i]! - y[i]!
  return 0
}

/** The solver lists every quantity of every offer; the owner compares suppliers. */
export function comparison(proposal: RecoveryProposal | null | undefined): Comparison {
  if (!proposal) return { wait: null, options: [], recommended: null }
  const groups = new Map<string, RecoveryCandidate[]>()
  for (const c of proposal.candidates)
    if (c.supplier_id && c.quantity > 0)
      groups.set(c.supplier_id, [...(groups.get(c.supplier_id) || []), c])
  const options = [...groups].map(([supplierId, list]) => {
    const feasible = list
      .filter((c) => c.feasible && c.executable)
      .sort((a, b) => a.quantity - b.quantity)
    const best = [...(feasible.length ? feasible : list)].sort(byRank)[0]!
    return {
      supplierId,
      best,
      feasible,
      blocked: feasible.length ? [] : [...new Set(list.flatMap((c) => c.rejection_reasons))],
    }
  })
  options.sort(
    (a, b) => Number(!a.feasible.length) - Number(!b.feasible.length) || byRank(a.best, b.best),
  )
  return {
    wait: proposal.candidates.find((c) => c.quantity === 0) || null,
    options,
    recommended:
      proposal.candidates.find((c) => c.id === proposal.recommended_candidate_id) || null,
  }
}

/** The settlement day a candidate's goods are counted in, if they arrive within the seven days. */
export const arrivalOf = (c: RecoveryCandidate | null | undefined) =>
  c?.daily.find((d) => d.proposed_arrivals > 0)?.settlement_at || null

/** One sentence that says what the comparison found; the long explanation stays folded. */
export function conclusion(cmp: Comparison, originals = true) {
  const before = cmp.wait?.lost_qty ?? 0
  const r = cmp.recommended
  if (!before) return t(originals ? '等原订单就够：7 天内不缺货。' : '不用补：7 天内不缺货。')
  if (!r || r.quantity === 0)
    return cmp.options.some((o) => o.feasible.length)
      ? t(
          originals
            ? '买了也赶不上：最快的报价到货时缺口已经出现，等原订单 7 天共缺 {0} 件。'
            : '买了也赶不上：最快的报价到货时缺口已经出现，7 天共缺 {0} 件。',
          [before],
        )
      : t('现有报价都补不上缺口：不补的话 7 天共缺 {0} 件。', [before])
  return named('{0}补 {1} 件最合适：7 天缺货从 {2} 件降到 {3} 件，花 {4}。', [
    supplierDisplayName(r.supplier_id),
    r.quantity,
    before,
    r.lost_qty,
    money(r.spend_minor),
  ])
}

const han = /[\u3400-\u9fff]/
/**
 * t() for a sentence that names a supplier (values[at]). A name that starts or ends with a Latin
 * letter or digit keeps a space from the Chinese next to it ("用供应商 001 补 40 件", "用 B 补
 * 40 件"), the way the templates already write "40 件"; Chinese names join directly ("用百川批发补
 * 40 件"). Only the edges of the name change: the name itself, the other values and English
 * sentences come out exactly as from t().
 */
export function named(source: string, values: Array<string | number>, at = 0) {
  const template = t(source)
  return template.replace(/\{(\d+)\}/g, (mark: string, index: string, offset: number) => {
    let value = String(values[Number(index)] ?? '')
    if (Number(index) !== at) return value
    if (han.test(template.charAt(offset - 1)) && /^[A-Za-z0-9]/.test(value)) value = ' ' + value
    if (han.test(template.charAt(offset + mark.length)) && /[A-Za-z0-9]$/.test(value)) value += ' '
    return value
  })
}

/** Keeps a number with its unit on one line ("7 天", "40 件", "40 units") wherever text wraps. */
export const unbroken = (text: string) => text.replace(/(\d) (?=\S)/g, '$1\u00a0')

/** A unit price as a price list prints it: ¥9.50, not ¥9.5 (amounts keep the shared money()). */
export const priceOf = (minor: number | null | undefined) =>
  minor == null
    ? t('未取得')
    : new Intl.NumberFormat(intlLocale(), {
        style: 'currency',
        currency: 'CNY',
        minimumFractionDigits: minor % 100 ? 2 : 0,
        maximumFractionDigits: 2,
        currencyDisplay: intlLocale() === 'en-SG' ? 'code' : 'symbol',
      }).format(minor / 100)

/** A settlement or delivery day as month and day, in the reader's locale. */
export const dayOf = (at: string | null | undefined) =>
  at
    ? new Date(at.length === 10 ? at + 'T00:00:00' : at).toLocaleDateString(intlLocale(), {
        month: 'numeric',
        day: 'numeric',
      })
    : t('尚未取得')

/** Solver and gate reasons in the owner's words; unknown codes are shown as sent. */
export const blockedReason = (code: string) =>
  t(
    {
      BUDGET_EXCEEDED: '超出本次预算',
      CASH_FLOOR_VIOLATION: '会低于现金底线',
      OFFER_EXPIRED: '报价已过期',
      MINIMUM_ORDER_QUANTITY: '不到起订量',
      PACK_SIZE_MISMATCH: '不符合整箱数量',
      ARRIVAL_WINDOW_MISSED: '7 天内送不到',
      ACTION_IN_PROGRESS: '另一笔采购还没处理完',
      EMERGENCY_PURCHASE_ALREADY_ACCEPTED: '这次应急补货已经买过一笔',
      TASK_QUANTITY_LIMIT: '超过数量上限',
      OFFER_SCOPE_MISMATCH: '报价不是这件商品',
      UNVERIFIED_EXECUTION_INPUT: '执行条件还没核实',
      MONEY_OVERFLOW: '金额超出范围',
    }[code] || code,
  )

/** A reply that accepts fewer units than ordered: the supplier can supply only part of it. */
export function partialReply(action: Schema<'Action'> | null | undefined) {
  const reply = action?.supplier_reply
  if (!reply || reply.outcome !== 'needs_attention' || reply.decision !== 'accepted') return null
  const quantity = reply.differences.find((d) => d.field === 'quantity')
  if (!quantity || Number(quantity.replied) >= Number(quantity.ordered)) return null
  return { ordered: Number(quantity.ordered), offered: Number(quantity.replied) }
}

export type Outcome = {
  /** Projected shortage over the seven days without and with this purchase. */
  before: number | null
  after: number | null
  spend: number
  received: number
  ordered: number
  supplierId: string | null
}

/**
 * The result line. Shortages are the plan's projection, not observed sales: the backend records
 * no actual outcome for a Case, so the summary says "预计".
 */
export function outcomeOf(
  plan: PlanDocument | null,
  action: Schema<'Action'> | null,
  inbound: Schema<'InboundItem'> | null,
  wait: RecoveryCandidate | null,
): Outcome {
  const candidates = plan?.candidates || []
  const chosen =
    plan && 'selected_candidate_id' in plan
      ? candidates.find((c) => c.id === plan.selected_candidate_id)
      : null
  const baseline = candidates.find((c) => c.quantity === 0)
  return {
    before: baseline?.shortage_qty ?? wait?.lost_qty ?? null,
    after: action && action.status === 'SUCCEEDED' ? (chosen?.shortage_qty ?? null) : null,
    spend: action?.status === 'SUCCEEDED' ? action.amount_minor : 0,
    received: inbound?.received_quantity ?? 0,
    ordered: inbound?.ordered_quantity ?? action?.quantity ?? 0,
    supplierId: action?.purchase_snapshot.supplier_id ?? null,
  }
}

/**
 * Whether a mission needs an emergency restock that its regular plan cannot give: a failed or
 * declined purchase, an overdue original order, a plan with no feasible purchase or one that still
 * leaves a gap, or cash that cannot cover the plan. A stockout the pending plan covers is not one.
 */
export function recoveryTrigger(input: {
  missionId: string
  plan: PlanDocument | null
  actions: Schema<'Action'>[]
  inbounds: Schema<'InboundItem'>[]
  alerts: Schema<'Alert'>[]
}): { reason: RecoveryReason; supplier?: string; gap?: number } | null {
  const latest = input.actions
    .filter((a) => a.mission_id === input.missionId)
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0]
  if (latest?.status === 'FAILED')
    return {
      reason: latest.supplier_reply?.outcome === 'declined' ? 'declined' : 'failed',
      supplier: latest.purchase_snapshot.supplier_id,
    }
  if (latest && ['QUEUED', 'EXECUTING', 'UNKNOWN'].includes(latest.status)) return null
  if (
    input.inbounds.some(
      (i) => i.mission_id === input.missionId && i.remaining_quantity > 0 && i.is_overdue,
    )
  )
    return { reason: 'late' }
  const plan = input.plan
  if (
    plan &&
    plan.mission_id === input.missionId &&
    plan.status === 'PENDING_APPROVAL' &&
    !('plan_kind' in plan)
  ) {
    const shortage = (quantity: number) =>
      plan.candidates.find((c) => c.quantity === quantity)?.shortage_qty ?? 0
    if (!plan.proposed_purchase && shortage(0) > 0)
      return { reason: 'infeasible', gap: shortage(0) }
    if (plan.proposed_purchase && shortage(plan.proposed_purchase.quantity) > 0)
      return { reason: 'stockout', gap: shortage(plan.proposed_purchase.quantity) }
  }
  if (
    input.alerts.some(
      (a) =>
        a.mission_id === input.missionId && a.status !== 'RESOLVED' && a.type === 'CASH_CONSTRAINT',
    )
  )
    return { reason: 'cash' }
  return null
}

/** Case and sourcing failures in the owner's words; others keep the shared API wording. */
export function caseProblem(code: string, message: string) {
  const words: Record<string, string> = {
    CASE_REVISION_CONFLICT: '这次应急补货刚有新变化，已重新读取，请再看一眼。',
    CASE_TERMINAL: '这次应急补货已经结束。',
    PROPOSAL_STALE: '比价结果已经变化，请重新比价。',
    PROPOSAL_HASH_CONFLICT: '比价结果已经变化，请重新比价。',
    PROPOSAL_INVALID: '比价结果已经变化，请重新比价。',
    PROPOSAL_REQUIRED: '先比价，再决定等原订单。',
    PLAN_EXPIRED: '比价结果已过期，请重新比价。',
    OFFER_EXPIRED: '这家的报价已过期，请重新找货。',
    OFFER_UNAVAILABLE: '有一家的报价不在档了，请重新找货。',
    EMERGENCY_PURCHASE_ALREADY_ACCEPTED: '这次应急补货已经买过一笔。',
    CANDIDATE_NOT_EXECUTABLE: '这个选项现在不能买，请换一个。',
    SOURCING_MODEL_NOT_CONFIGURED: '读供应商资料需要服务端配置模型；先比较已在档的报价。',
    SUPPLIER_DOCUMENTS_REQUIRED: '还没有供应商资料；先比较已在档的报价。',
    NO_SHORTFALL: '等原订单就够，不用再找货。',
    SOURCING_IN_PROGRESS: '正在读供应商资料，稍等。',
    SOURCING_INTERRUPTED: '读资料被中断了，可以重新找货。',
    SOURCING_UNAVAILABLE: '暂时读不了供应商资料，可以稍后重新找货。',
    CASE_INPUT_CHANGED: '读资料期间条件改了，读出的报价没有登记，请重新找货。',
    DAILY_DEMAND_REQUIRED: '需要七天的需求：没有可用的日预测，请按每天件数填写。',
    RECOVERY_INPUT_INVALID: '经营时钟已经往前走了，需求日期要按现在重排，请重新比价。',
    OFFER_SELECTION_REQUIRED: '在档报价超过三家，请重新比价，系统会取最便宜的三家。',
    FORECAST_UNAVAILABLE: '当前预测不可用，请按每天件数填写需求。',
    BUSINESS_TIME_REQUIRED: '经营时钟还没有同步，稍后再试。',
    INBOUND_STATE_MISMATCH: '在途订单和库存对不上，稍后再试。',
    SEARCH_SPACE_EXCEEDED: '可选数量太多，请把预算调低一些。',
    MISSION_NOT_ACTIVE: '备货委托已暂停或结束，不能发起应急补货。',
  }
  return t(words[code] || message)
}
