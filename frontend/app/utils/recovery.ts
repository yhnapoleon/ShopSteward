import { intlLocale, t } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import type { PlanDocument, Schema } from '~/types/models'
import type { RecoveryCandidate, RecoveryCase, RecoveryProposal, Sourcing } from '~/types/recovery'

// Emergency restock (应急补货) as one flow on the work page: one Case, one progress line, the next
// step always in the same place. Everything here is derived from the recovery Case, its plan and
// its purchases; nothing writes business data. Quantities follow the recovery solver's own
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
/** Whose move it is: the owner, the system, someone else (who may approve), or nobody (over). */
export type Actor = 'you' | 'system' | 'other' | 'done'
/** Who sends the order: the owner by hand (assisted) or the supplier's system (direct). */
export type Channel = 'assisted' | 'direct'
/** buy: an order the owner sends; direct: the connected supplier's system; wait: no purchase. */
export type FlowVariant = 'buy' | 'direct' | 'wait'
export type Again =
  | 'pending'
  | 'declined'
  | 'failed'
  | 'withdrawn'
  | 'short'
  | 'rejected'
  | 'recheck'
  | 'expired'
  | 'stale'
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
 * when no original order is on the way means not restocking at all: that flow has four steps, and
 * it stays on the decision until the owner ends it (the backend never settles it by itself).
 */
export const flowSteps = (variant: FlowVariant, originals = true): FlowStep[] =>
  variant === 'wait' && !originals
    ? [
        { key: 'brief', label: '说明情况' },
        { key: 'compare', label: '找货比价' },
        { key: 'receive', label: '决定这次不补' },
        { key: 'result', label: '结果' },
      ]
    : STEPS[variant]

/**
 * One purchase the Case led to, oldest first (the backend's `purchases`, joined with the shop's
 * order list for whatever it has read more recently). `accepted` is what the supplier confirmed,
 * `received` what has arrived of it. Receiving goods never closes a restock whose latest order
 * was filled only in part: the backend settles it only once the rest was bought elsewhere or the
 * owner chose to stop there (lifecycle.gap_open).
 */
export type Purchase = {
  actionId: string
  supplierId: string
  supplierName: string
  status: string
  planned: number
  accepted: number
  received: number
  arrivalAt?: string
  /** The Case's current order (the one its latest adopted plan led to). */
  current: boolean
  /** Sent by the owner: its goods are recorded by hand, nothing reports them. */
  byHand: boolean
}

export type FlowFacts = {
  detail: RecoveryCase | null
  /** The Case's own purchase order, read from the shop's order list. */
  action: Schema<'Action'> | null
  inbound: Schema<'InboundItem'> | null
  /** Original orders the Case's analysis counted on (the waiting variant watches them). */
  originals: Schema<'InboundItem'>[]
  /** Every purchase of the Case (purchasesOf); settling waits for all of them. */
  purchases?: Purchase[]
  /** Whether the current identity may approve (confirm, record replies); else someone else does. */
  approver?: boolean
  /** Whether the current identity may operate (record arrivals, end the restock). */
  operator?: boolean
  /** How the Case's order goes out, known before the shop lists it. */
  channel?: Channel | null
}
export type FlowState = {
  variant: FlowVariant
  stage: StageKey
  actor: Actor
  /** The Case is over (settled, ended or closed): it shrinks to one summary line. */
  ended: boolean
  /** Comparing again, and why. */
  again: Again | null
}
export const TERMINAL = ['CANCELLED', 'CLOSED', 'RESOLVED']
const IN_FLIGHT = ['QUEUED', 'EXECUTING', 'UNKNOWN']
/** Order statuses after which nothing more happens to the order itself. */
const SETTLED = ['SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE']
const state = (
  variant: FlowVariant,
  stage: StageKey,
  actor: Actor,
  ended = false,
  again: Again | null = null,
): FlowState => ({ variant, stage, actor, ended, again })

/** A purchase the supplier filled only in part: what was taken and what is still missing. */
export function shortfall(action: Schema<'Action'> | null | undefined) {
  if (!action || action.status !== 'SUCCEEDED') return null
  const accepted = action.receipt?.quantity ?? action.quantity
  if (accepted >= action.quantity) return null
  return { accepted, ordered: action.quantity, missing: action.quantity - accepted }
}

/** An order the shop lists says how it went out; one it has not read yet goes by the hint. */
const variantOf = (action: Schema<'Action'> | null, channel?: Channel | null): FlowVariant =>
  action
    ? action.channel === 'assisted'
      ? 'buy'
      : 'direct'
    : channel === 'direct'
      ? 'direct'
      : 'buy'

/** The Case's own reading of its order (execution_status) when no fresher read has it. */
function caseOrderStatus(d: RecoveryCase) {
  const status = d.execution_status
  if (!status) return null
  if (['ACCEPTED', 'PARTIALLY_RECEIVED', 'RECEIVED'].includes(status)) return 'SUCCEEDED'
  // Without an order the backend reports the plan's status here; that is not an order status.
  return [...IN_FLIGHT, ...SETTLED].includes(status) ? status : null
}

/** Why the Case compares again after an order that bought nothing. */
const againAfter = (status: string, action: Schema<'Action'> | null): Again =>
  status === 'CANCELLED'
    ? 'withdrawn'
    : status === 'STALE'
      ? 'recheck'
      : action?.supplier_reply?.outcome === 'declined'
        ? 'declined'
        : 'failed'

/**
 * The Case's own order: the one its adopted plan led to. The backend creates it as the plan is
 * approved, so until the Case is read again the shop's orders already show it by that plan.
 */
export function caseAction(d: RecoveryCase | null | undefined, actions: Schema<'Action'>[]) {
  if (!d) return null
  return (
    (d.action_id && actions.find((a) => a.id === d.action_id)) ||
    (d.plan_id && actions.find((a) => a.plan_id === d.plan_id)) ||
    null
  )
}

/**
 * Original orders: those the Case's analysis counted on (in transit when it was analyzed), never
 * the Case's own purchases, which an analysis after a partial supply also sees on their way.
 */
export function originalOrders(
  d: RecoveryCase | null | undefined,
  inbounds: Schema<'InboundItem'>[],
) {
  if (!d) return []
  const own = new Set([...(d.purchases || []).map((p) => p.action_id), d.action_id || ''])
  const ids = new Set(
    d.evidence.filter((e) => e.kind === 'inbound_order' && !own.has(e.id)).map((e) => e.id),
  )
  return inbounds.filter((i) => ids.has(i.action_id))
}
/** Whether waiting means waiting for an original order: one was counted on, with units ordered. */
export const hasOriginals = (orders: Schema<'InboundItem'>[]) =>
  orders.some((i) => i.ordered_quantity > 0)

/**
 * The Case's purchases, oldest first, each with the fresher of the Case's and the shop's reads:
 * a settled order status wins over one still in flight, arrivals take the larger count.
 * `readable` tells a supplier known only from its documents (the backend leaves its order to
 * the owner) when the shop has not listed the order yet.
 */
export function purchasesOf(
  d: RecoveryCase | null | undefined,
  actions: Schema<'Action'>[],
  inbounds: Schema<'InboundItem'>[],
  readable: (supplierId: string) => boolean = () => false,
): Purchase[] {
  if (!d) return []
  const rows: Schema<'CasePurchase'>[] = [...(d.purchases || [])]
  // An order the shop already lists that this read of the Case does not carry yet.
  const latest = caseAction(d, actions)
  const latestId = d.action_id ?? latest?.id ?? null
  // The current purchase belongs to the current revision: after a revision (finding the rest
  // elsewhere, or deciding to wait) an earlier order is one more purchase, not the current one.
  const fresh = (d.plan_revision ?? d.current_revision) >= d.current_revision
  if (latest && !rows.some((p) => p.action_id === latest.id))
    rows.push({
      action_id: latest.id,
      supplier_id: latest.purchase_snapshot.supplier_id,
      status: latest.status,
      planned_qty: latest.quantity,
      accepted_qty: null,
      received_qty: null,
    })
  return rows.map((p) => {
    const a = actions.find((x) => x.id === p.action_id) || null
    const inbound = inbounds.find((i) => i.action_id === p.action_id) || null
    const status =
      a && (SETTLED.includes(a.status) || !SETTLED.includes(p.status)) ? a.status : p.status
    const bought = status === 'SUCCEEDED'
    const accepted = bought
      ? (inbound?.ordered_quantity ?? p.accepted_qty ?? a?.receipt?.quantity ?? p.planned_qty)
      : 0
    const received = bought
      ? Math.min(accepted, Math.max(inbound?.received_quantity ?? 0, p.received_qty ?? 0))
      : 0
    const arrivalAt =
      inbound?.expected_arrival_at ||
      a?.supplier_reply?.delivery_date ||
      a?.purchase_snapshot.expected_arrival_at ||
      null
    return {
      actionId: p.action_id,
      supplierId: p.supplier_id,
      supplierName: supplierDisplayName(p.supplier_id),
      status,
      planned: p.planned_qty,
      accepted,
      received,
      ...(arrivalAt ? { arrivalAt } : {}),
      current: p.action_id === latestId && fresh,
      // Only an order sent by hand can be taken in part (execution/assisted.py accept_partial).
      byHand: a
        ? a.channel === 'assisted'
        : readable(p.supplier_id) || (bought && accepted < p.planned_qty),
    }
  })
}

/**
 * Where the Case stands, read from the backend's facts. The backend settles a Case itself
 * (RESOLVED, with its outcome) once every purchase it decided on has arrived; until then goods
 * that are all in read as being settled, never as a result the page made up. An order the shop
 * has not listed yet is read from the Case, so a refresh in between never steps back.
 */
export function flowState(facts: FlowFacts): FlowState {
  const { detail: d, action: a, inbound, originals } = facts
  const purchases = facts.purchases ?? []
  if (!d) return state('buy', 'brief', 'you')
  const terminal = TERMINAL.includes(d.status)
  const waited = d.outcome?.path === 'waiting'
  const variant = variantOf(a, facts.channel)
  // The owner's move, when this identity may not make it, waits on someone who may.
  const by = (actor: Actor, allowed: boolean | undefined): Actor =>
    actor === 'you' && allowed === false ? 'other' : actor
  if (d.status === 'RESOLVED') return state(waited ? 'wait' : variant, 'result', 'done', true)
  const own = purchases.find((p) => p.current)
  // An order that bought nothing is no longer the Case's (`action_id` is cleared), yet the Case
  // still reports how it ended, which says why it compares again.
  const status = own?.status ?? a?.status ?? caseOrderStatus(d)
  if (status) {
    // Revised since this order was placed: the newer revision decides the stage, not the order.
    const current = (d.plan_revision ?? d.current_revision) >= d.current_revision
    if (status === 'SUCCEEDED') {
      const short = own ? own.accepted < own.planned : !!shortfall(a)
      if (!short || terminal) {
        // Settling waits for every purchase of the Case, not only the latest one.
        const open = purchases.filter((p) => p.status === 'SUCCEEDED' && p.received < p.accepted)
        const arrived = purchases.length
          ? !open.length
          : inbound
            ? inbound.remaining_quantity === 0
            : d.execution_status === 'RECEIVED'
        if (arrived)
          return terminal
            ? state(variant, 'result', 'done', true)
            : state(variant, 'receive', 'system')
        // Goods still on the way: the owner records what was sent by hand; a Case ended by hand
        // keeps them visible as a summary.
        const byHand = purchases.length ? open.some((p) => p.byHand) : variant === 'buy'
        return state(variant, 'receive', by(byHand ? 'you' : 'system', facts.operator), terminal)
      }
      // Taken in part: the rest is found elsewhere in this Case, while that part is on its way.
      if (current) return state('buy', 'compare', 'you', false, 'short')
    } else if (IN_FLIGHT.includes(status)) {
      // Recording the supplier's reply takes the approval right, as confirming does.
      return state(
        variant,
        'order',
        by(status === 'EXECUTING' && variant === 'buy' ? 'you' : 'system', facts.approver),
      )
    } else {
      // Declined, failed, withdrawn or void: nothing was bought, so compare again.
      if (terminal) return state('buy', 'result', 'done', true)
      if (current) return state('buy', 'compare', 'you', false, againAfter(status, a))
    }
  }
  if (terminal) return state(waited ? 'wait' : 'buy', 'result', 'done', true)
  // What the owner decided for the current revision, if a plan was adopted from it.
  const decided = d.plan_id && d.plan_revision === d.current_revision ? d.plan_status : null
  // Approved, its order not read yet: the purchase is being placed.
  if (decided === 'APPROVED') return state(variant, 'order', 'system')
  // The owner chose to wait: the Case watches the original orders until they are in. Goods an
  // earlier order of this restock bought settle it instead once they are in (lifecycle.settle);
  // those sent by hand are recorded by the owner. Waiting with nothing on the way is not
  // restocking at all: it holds the daily suggestions until it is ended.
  if (d.status === 'MONITORING' && decided !== 'PENDING_APPROVAL') {
    const bought = purchases.filter((p) => p.status === 'SUCCEEDED')
    const open = bought.filter((p) => p.received < p.accepted)
    const actor: Actor = bought.length
      ? open.some((p) => p.byHand)
        ? 'you'
        : 'system'
      : hasOriginals(originals)
        ? 'system'
        : 'you'
    return state('wait', 'receive', by(actor, facts.operator))
  }
  if (decided === 'PENDING_APPROVAL')
    return state(variant, 'confirm', facts.approver === false ? 'other' : 'you')
  // The owner turned the plan down; the Case still holds the item until it is ended.
  if (decided === 'REJECTED') return state('buy', 'compare', 'you', false, 'rejected')
  if (decided === 'EXPIRED' || decided === 'SUPERSEDED')
    return state(
      'buy',
      'compare',
      'you',
      false,
      d.status === 'RECHECK_REQUIRED' ? 'recheck' : 'expired',
    )
  if ((d.sourcing as Sourcing | null | undefined)?.status === 'running')
    return state('buy', 'compare', 'system')
  if (d.status === 'OPTIONS_READY' && d.proposal)
    return state('buy', 'compare', 'you', false, d.stale ? 'stale' : null)
  if (d.status === 'NEEDS_INPUT' || d.status === 'BLOCKED')
    return state('buy', 'compare', 'you', false, 'input')
  if (d.status === 'RECHECK_REQUIRED') return state('buy', 'compare', 'you', false, 'recheck')
  // Created or revised but never analyzed: the analysis this page started failed (its reason is
  // shown beside the card) or never ran. Analyses run inside the request, so nothing is pending.
  return state('buy', 'compare', 'you', false, 'pending')
}

/**
 * Why the comparison has to be done again, as one sentence with one cause (never "this or
 * that"): the reason the flow compares again, with the backend's recheck reason folded in.
 */
export function againDetail(input: {
  again: Again | null
  detail: RecoveryCase | null
  action: Schema<'Action'> | null
  purchases?: Purchase[]
  now?: number
}): string {
  const { again, detail: d, action: a } = input
  const own = input.purchases?.find((p) => p.current)
  const name = supplierDisplayName(a?.purchase_snapshot.supplier_id ?? own?.supplierId)
  switch (again) {
    case null:
      return ''
    case 'declined':
      return named('{0}拒单，预留资金已释放。', [name])
    case 'withdrawn':
      return named('给{0}的订单已撤回，预留资金已释放。', [name])
    case 'failed':
      return recheckReason('PURCHASE_FAILED')
    case 'short': {
      const short =
        shortfall(a) ||
        (own && own.accepted < own.planned
          ? { accepted: own.accepted, ordered: own.planned, missing: own.planned - own.accepted }
          : null)
      return short
        ? named('{0}确认了 {1} 件（订单 {2} 件），已按 {1} 件成交；还缺 {3} 件。', [
            name,
            short.accepted,
            short.ordered,
            short.missing,
          ])
        : ''
    }
    case 'rejected':
      return t('你没有采用这份应急方案。结束这次应急补货后，系统才恢复每天的补货建议。')
    case 'recheck':
      return recheckReason(
        d?.recheck_reason || ((own?.status ?? a?.status) === 'STALE' ? 'PURCHASE_STALE' : null),
      )
    case 'expired':
      return t('待确认的应急方案已过期。')
    case 'stale':
      return d?.proposal && Date.parse(d.proposal.expires_at) <= (input.now ?? Date.now())
        ? t('比价结果已超过有效期。')
        : t('比价之后经营数据有变化，比价结果不再成立。')
    case 'pending':
      return t('还没有比价结果。')
    case 'input':
      return caseProblem(d?.missing_inputs[0] || '', t('比价缺少条件。'))
  }
}

/** A supplier that can give only part of an order: still to decide, or already taken. */
export type PartialSupply = {
  supplierName: string
  ordered: number
  offered: number
  unitMinor: number
  payMinor: number
  releaseMinor: number
  missing: number
  /** Taken at the smaller quantity (the rest is found elsewhere); false while still to decide. */
  taken: boolean
}
export function partialOf(action: Schema<'Action'> | null | undefined): PartialSupply | null {
  if (!action) return null
  const unit = action.purchase_snapshot.unit_price_minor
  const short = shortfall(action)
  const reply = short ? null : action.status === 'EXECUTING' ? partialReply(action) : null
  const offered = short?.accepted ?? reply?.offered
  if (offered == null) return null
  const pay = (short && action.receipt?.total_minor) || offered * unit
  return {
    supplierName: supplierDisplayName(action.purchase_snapshot.supplier_id),
    ordered: action.quantity,
    offered,
    unitMinor: unit,
    payMinor: pay,
    releaseMinor: Math.max(0, action.amount_minor - pay),
    missing: action.quantity - offered,
    taken: !!short,
  }
}

/** Why the backend asks for a new comparison (`recheck_reason`), as the owner reads it. */
export function recheckReason(code: string | null | undefined) {
  const reasons: Record<string, string> = {
    PLAN_EXPIRED: '待确认的应急方案已过期。',
    OPTIONS_EXPIRED: '比价结果已超过有效期。',
    BUSINESS_STATE_CHANGED: '库存、现金或营业时间变了，比价结果不再成立。',
    MISSION_CHANGED: '备货委托的设置变了，比价结果不再成立。',
    SOURCE_STALE: '经营数据没有按时同步，比价结果需要更新。',
    PURCHASE_FAILED: '这笔采购没有成功，预留资金已释放。',
    PURCHASE_CANCELLED: '这笔采购已取消，预留资金已释放。',
    PURCHASE_STALE: '原方案已失效，这笔采购没有执行。',
  }
  return t(reasons[code || ''] || '比价结果需要更新。')
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
  forecast?: { usable_for_planning: boolean; forecast: object | null } | null
  plan?: PlanDocument | null
  remainingDemand?: number | null
}): DemandPlan {
  const doc = (input.forecast?.usable_for_planning ? input.forecast.forecast : null) as Record<
    string,
    unknown
  > | null
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
          ? '{0}只能供应一部分，缺的找别家补上；按当前需求，7 天内暂不缺货。'
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
    partial: '{2}只能供应一部分，缺的找别家补上：不补的话 {0} 起缺货，7 天共缺 {1} 件。',
  }
  return named(template[reason], [from, lost, name], 2)
}

/**
 * The comparison without the suppliers this restock left out. When the recommendation was one of
 * them, the best of what is left is recommended, by the solver's own order (least shortage,
 * then least spend), waiting included.
 */
export function withoutSuppliers(cmp: Comparison, excluded: ReadonlySet<string>): Comparison {
  if (!excluded.size) return cmp
  const options = cmp.options.filter((o) => !excluded.has(o.supplierId))
  const r = cmp.recommended
  if (!r || !r.supplier_id || !excluded.has(r.supplier_id)) return { ...cmp, options }
  const pool = [
    ...(cmp.wait ? [cmp.wait] : []),
    ...options.filter((o) => o.feasible.length).map((o) => o.best),
  ]
  return { ...cmp, options, recommended: [...pool].sort(byRank)[0] ?? null }
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
      UNVERIFIED_EXECUTION_INPUT: '下单条件还没确认',
      MONEY_OVERFLOW: '金额超出范围',
    }[code] || code,
  )

/** A reply that accepts fewer units than ordered: the supplier can supply only part of it. */
export function partialReply(action: Schema<'Action'> | null | undefined) {
  const reply = action?.supplier_reply
  if (!action || reply?.outcome !== 'partial' || reply.quantity == null) return null
  if (reply.quantity >= action.quantity) return null
  return { ordered: action.quantity, offered: reply.quantity }
}

export type Outcome = {
  /** Projected shortage over the seven days without and with what was done. */
  before: number | null
  after: number | null
  spend: number
  received: number
  /** Units bought (accepted by the suppliers) and units first ordered. */
  ordered: number
  planned: number | null
  supplierId: string | null
  suppliers: string[]
  /** What each purchase brought, in order: "Baichuan Wholesale 10 + Anhe Trading 30". */
  parts: { supplierId: string; quantity: number }[]
  path: 'purchase' | 'waiting' | null
}
/**
 * What the restock achieved: the backend's outcome once it settled the Case; before that (a Case
 * ended by hand) what the plan projected and the order shows.
 */
export function outcomeOf(
  detail: RecoveryCase | null,
  plan: PlanDocument | null,
  action: Schema<'Action'> | null,
  inbound: Schema<'InboundItem'> | null,
  wait: RecoveryCandidate | null,
): Outcome {
  const o = detail?.outcome
  if (o) {
    const suppliers = [
      ...new Set(
        (detail?.purchases || [])
          .filter((p) => o.action_ids.includes(p.action_id))
          .map((p) => p.supplier_id),
      ),
    ]
    const parts = (detail?.purchases || [])
      .filter((p) => o.action_ids.includes(p.action_id))
      .map((p) => ({ supplierId: p.supplier_id, quantity: p.accepted_qty ?? 0 }))
    return {
      before: o.lost_qty_before,
      after: o.lost_qty_after,
      spend: o.spend_minor,
      received: o.received_qty,
      ordered: o.purchased_qty,
      planned: o.planned_qty,
      supplierId: suppliers[0] ?? null,
      suppliers,
      parts,
      path: o.path,
    }
  }
  const candidates = plan?.candidates || []
  const chosen =
    plan && 'selected_candidate_id' in plan
      ? candidates.find((c) => c.id === plan.selected_candidate_id)
      : null
  const baseline = candidates.find((c) => c.quantity === 0)
  const supplierId = action?.purchase_snapshot.supplier_id ?? null
  return {
    before: baseline?.shortage_qty ?? wait?.lost_qty ?? null,
    after: action && action.status === 'SUCCEEDED' ? (chosen?.shortage_qty ?? null) : null,
    spend: action?.status === 'SUCCEEDED' ? action.amount_minor : 0,
    received: inbound?.received_quantity ?? 0,
    ordered: inbound?.ordered_quantity ?? action?.quantity ?? 0,
    planned: null,
    supplierId,
    suppliers: supplierId ? [supplierId] : [],
    parts:
      supplierId && action?.status === 'SUCCEEDED'
        ? [{ supplierId, quantity: inbound?.ordered_quantity ?? action.quantity }]
        : [],
    path: null,
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
    OFFER_UNAVAILABLE: '有一家的报价已经没有了，请重新找货。',
    EMERGENCY_PURCHASE_ALREADY_ACCEPTED: '这次应急补货已经买过一笔。',
    CANDIDATE_NOT_EXECUTABLE: '这个选项现在不能买，请换一个。',
    SOURCING_MODEL_NOT_CONFIGURED: '现在读不了供应商资料；先比较已有的报价。',
    SUPPLIER_DOCUMENTS_REQUIRED: '还没有供应商资料；先比较已有的报价。',
    NO_SHORTFALL: '等原订单就够，不用再找货。',
    SOURCING_IN_PROGRESS: '正在读供应商资料，稍等。',
    SOURCING_INTERRUPTED: '读资料被中断了，可以重新找货。',
    SOURCING_UNAVAILABLE: '暂时读不了供应商资料，可以稍后重新找货。',
    CASE_INPUT_CHANGED: '读资料期间条件改了，读出的报价没有登记，请重新找货。',
    // Comparing again fills in the mission's demand assumption day by day (useRecoveryFlow.again).
    DAILY_DEMAND_REQUIRED: '没有可用的日预测；重新比价会按当前需求假设逐日计算。',
    RECOVERY_INPUT_INVALID: '比价条件不完整或有误，请重新比价。',
    CASE_ALREADY_OPEN: '这件商品已有一次应急补货在进行，先处理完它。',
    CASE_REFRESH_REQUIRED: '这次比价结果已不成立，请重新比价。',
    NO_OTHER_SUPPLIERS: '在档的供应商都已排除，没有别家可以找。',
    OFFER_SELECTION_REQUIRED: '能比的报价超过三家；重新比价会取最便宜的三家。',
    FORECAST_UNAVAILABLE: '当前预测不可用；重新比价会按当前需求假设逐日计算。',
    DATA_STALE: '经营数据还未同步完成，稍后再比价。',
    ACTION_IN_PROGRESS: '另一笔采购还没处理完，处理完再采用这一笔。',
    PLAN_VERSION_CONFLICT: '经营情况刚有变化，已重新读取，请再看一眼。',
    // The analysis froze the business state; adopting needs it unchanged (validation.py).
    STATE_VERSION_CONFLICT: '经营数据刚变了，重新比价后再采用。',
    BUSINESS_TIME_REQUIRED: '经营时钟还没有同步，稍后再试。',
    INBOUND_STATE_MISMATCH: '在途订单和库存对不上，稍后再试。',
    SEARCH_SPACE_EXCEEDED: '可选数量太多，请把预算调低一些。',
    MISSION_NOT_ACTIVE: '备货委托已暂停或结束，不能发起应急补货。',
  }
  return t(words[code] || message)
}
