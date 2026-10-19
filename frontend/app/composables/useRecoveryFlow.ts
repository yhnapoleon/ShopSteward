import type { InjectionKey } from 'vue'
import { t } from '~/i18n'
import { api, ApiFailure, query } from '~/utils/api'
import type { PlanDocument } from '~/types/models'
import type { ForecastCurrent } from '~/types/forecast'
import type { RecoveryCandidate, RecoveryCase, Sourcing } from '~/types/recovery'
import {
  againDetail as againSentence,
  caseAction,
  comparison,
  demandFrom,
  flowState,
  hasOriginals as anyOriginals,
  originalOrders,
  partialOf,
  purchasesOf,
  settlements,
  withoutSuppliers,
  type Actor,
  type Channel,
  type DemandPlan,
  type RecoveryLaunch,
} from '~/utils/recovery'
import { SAMPLE_DISTRICT } from '~/composables/useSupplierDirectory'

// The emergency restock flow of one mission (workspace §18). It drives the recovery Case through
// the existing endpoints: create and analyze, source, materialize, wait, cancel; the purchase
// itself is confirmed in the page's approval dialog and its orders handled by the shop's own
// commands. Nothing here approves a purchase on its own.

const EXCLUDED = 'ss.recovery.excluded:'
/** How often the Case is read while the system works on it (suppliers, analysis, an order). */
const POLL_FAST_MS = 2000
/** How often otherwise, including while goods or original orders take their days to arrive. */
const POLL_SLOW_MS = 6000
/** A call of ours shows as "系统在做" only once it takes longer than this. */
const SLOW_CALL_MS = 300

export function useRecoveryFlow(missionId: () => string) {
  const shop = useShop()
  const { s } = shop
  const recovery = useRecoveryCase(missionId)
  const directory = useSupplierDirectory()
  const launcher = useRecoveryLaunch()
  const demo = useDemoMode()
  const { detail } = recovery
  /** The brief is open for this request; no Case exists for it yet. */
  const brief = ref<RecoveryLaunch | null>(null)
  const forecast = ref<ForecastCurrent | null>(null)
  const planDoc = ref<PlanDocument | null>(null)
  /** A step this page is running between backend calls. */
  const working = ref('')
  /** The running call has taken long enough to say the system is working on it. */
  const slow = ref(false)
  /** The last failure of a call made here (sourcing, withdrawal, reply, arrival). */
  const problem = ref<{ code: string; message: string } | null>(null)
  /** Bumped when a request asks the flow to be looked at; the card scrolls into view. */
  const focus = ref(0)
  /** The owner looks at the other quotes again while an adopted plan waits ("换一家"). */
  const revisiting = ref(false)
  /** The first complete state (the Case with its purchases, and their orders) has arrived. */
  const loaded = ref(false)
  let previousCase = ''

  const operator = computed(() => shop.hasRole('operator'))
  const approver = computed(() => shop.hasRole('approver'))
  const sourcing = computed(() => (detail.value?.sourcing as Sourcing | null | undefined) || null)
  const proposal = computed(() => detail.value?.proposal || null)
  /** The Case's order; right after confirming it is found by its plan before the Case says so. */
  const action = computed(() => caseAction(detail.value, s.actions))
  const inbound = computed(
    () => (action.value && s.inbounds.find((i) => i.action_id === action.value!.id)) || null,
  )
  /** A supplier known from its documents or a sourcing run has no ordering system of its own. */
  const fromDocuments = (supplierId: string) =>
    directory.readable.value.some((x) => x.supplier_id === supplierId) ||
    !!sourcing.value?.suppliers.some((x) => x.supplier_id === supplierId)
  /** Every purchase of the Case, oldest first, with what has arrived of each. */
  const purchases = computed(() => purchasesOf(detail.value, s.actions, s.inbounds, fromDocuments))
  /** Original orders the analysis counted on, never this Case's own purchases. */
  const originals = computed(() => originalOrders(detail.value, s.inbounds))
  const hasOriginals = computed(() => anyOriginals(originals.value))
  /** The Case's plan: the shop's current plan while it waits, otherwise the stored document. */
  const casePlan = computed(() =>
    detail.value?.plan_id && shop.plan.value?.id === detail.value.plan_id
      ? shop.plan.value
      : planDoc.value?.id === detail.value?.plan_id
        ? planDoc.value
        : null,
  )
  /**
   * Who sends an order to this supplier, before any order exists: one read from documents always
   * gets it from the owner (execution/repository.py); otherwise an earlier order to it tells.
   * Null when nothing does (the deployment's purchase channel decides).
   */
  function channelFor(supplierId: string | null | undefined): Channel | null {
    if (!supplierId) return null
    if (fromDocuments(supplierId)) return 'assisted'
    const earlier = s.actions.find((a) => a.purchase_snapshot.supplier_id === supplierId)
    return earlier ? (earlier.channel === 'assisted' ? 'assisted' : 'direct') : null
  }
  /** How the Case's order goes (or will go) out: its order once it exists, else its plan's supplier. */
  const channel = computed<Channel | null>(() => {
    if (action.value) return action.value.channel === 'assisted' ? 'assisted' : 'direct'
    return channelFor(casePlan.value?.proposed_purchase?.supplier_id)
  })
  const flow = computed(() =>
    brief.value
      ? flowState({ detail: null, action: null, inbound: null, originals: [] })
      : flowState({
          detail: detail.value,
          action: action.value,
          inbound: inbound.value,
          originals: originals.value,
          purchases: purchases.value,
          approver: approver.value,
          operator: operator.value,
          channel: channel.value,
        }),
  )

  /** Suppliers this Case left out on purpose (sessionStorage), per Case. */
  const stored = ref<Record<string, string[]>>({})
  /**
   * Who stays out of this Case's comparisons: every supplier whose order failed, was taken back
   * or could be filled only in part, and every one the owner chose not to ask again ("不找…").
   */
  const excludedIds = computed(() => {
    const ids = new Set<string>()
    if (brief.value) {
      if (brief.value.exclude) ids.add(brief.value.exclude)
      return ids
    }
    const value = detail.value
    if (!value) return ids
    for (const id of stored.value[value.id] || []) ids.add(id)
    for (const p of purchases.value)
      if (
        p.status === 'FAILED' ||
        p.status === 'CANCELLED' ||
        (p.status === 'SUCCEEDED' && p.accepted < p.planned)
      )
        ids.add(p.supplierId)
    return ids
  })
  const isExcluded = (supplierId: string | null | undefined) =>
    !!supplierId && excludedIds.value.has(supplierId)
  /** The comparison without them; the recommendation is the best of what is left. */
  const cmp = computed(() => withoutSuppliers(comparison(proposal.value), excludedIds.value))
  /** Something was bought in this restock: it settles once that is in, whatever else is chosen. */
  const hasBought = computed(() => purchases.value.some((p) => p.status === 'SUCCEEDED'))

  /**
   * A submission whose answer never came back (a 5xx or a dropped connection) may or may not have
   * taken effect, so nothing else writes until it is sent again under its original key; the
   * backend then answers with what it did the first time.
   */
  // A submission in flight is not unconfirmed yet: it becomes so only once its answer is lost
  // (or when the page reloads with one pending). Sending it again keeps showing it as such.
  const unconfirmed = computed(
    () => !!recovery.pending.value && (!recovery.busy.value || working.value === 'retry'),
  )
  const inProgress = computed(
    () => !!brief.value || unconfirmed.value || (!!detail.value && !flow.value.ended),
  )
  /**
   * Whose move it is, as the progress line says it. Our own call counts as the system working
   * only once it is slow; a quick one leaves the next step where it is, showing that it waits.
   */
  const actor = computed<Actor>(() =>
    working.value && slow.value ? 'system' : unconfirmed.value ? 'you' : flow.value.actor,
  )
  /**
   * Everything is in: the backend settles the Case in the same step. Goods bought in this
   * restock decide it whenever there are any (lifecycle.settle), the original orders otherwise.
   */
  const settling = computed(() => {
    const state = flow.value
    if (state.stage !== 'receive' || state.ended) return false
    const bought = purchases.value.filter((p) => p.status === 'SUCCEEDED')
    if (bought.length) return bought.every((p) => p.received >= p.accepted)
    if (state.variant === 'wait')
      return hasOriginals.value && originals.value.every((i) => i.remaining_quantity === 0)
    return !!inbound.value && inbound.value.remaining_quantity === 0
  })
  /** A supplier that can give only part of the order: the decision, or what was taken. */
  const partial = computed(() => partialOf(action.value))
  /** Why the comparison needs doing again, as one cause. */
  const againDetail = computed(() =>
    againSentence({
      again: flow.value.again,
      detail: detail.value,
      action: action.value,
      purchases: purchases.value,
    }),
  )
  /** The adopted plan can be confirmed now, by this identity. */
  const canConfirm = computed(
    () =>
      flow.value.stage === 'confirm' &&
      !!casePlan.value &&
      approver.value &&
      shop.plan.value?.id === casePlan.value.id &&
      shop.canDecide.value,
  )
  /** Why the adopted plan cannot be confirmed right now: the one cause that holds, or nothing. */
  const unavailableReason = computed(() => {
    const plan = casePlan.value
    if (flow.value.stage !== 'confirm' || !plan || canConfirm.value) return ''
    if (!approver.value) return t('确认采购需要审批权限；有权限的人打开这件事就能确认。')
    if (s.pending) return t('上一笔采购确认的结果还没取得，先核实它。')
    if (!s.connected) return t('连接中断了，恢复后才能确认。')
    if (s.dashboard?.freshness.status !== 'FRESH') return t('经营数据还在同步，同步后就能确认。')
    if (shop.unresolved.value) return t('另一笔采购还没处理完，处理完再确认这一笔。')
    if (detail.value?.plan_status === 'EXPIRED' || Date.parse(plan.expires_at) <= Date.now())
      return t('这份应急方案已过期，需要重新比价。')
    if (shop.mission.value?.status === 'PAUSED') return t('备货委托已暂停，恢复后才能确认。')
    if (shop.mission.value?.status !== 'ACTIVE') return t('备货委托已结束，不能确认采购。')
    if (shop.plan.value?.id !== plan.id) return t('正在读取这份应急方案。')
    if (s.dashboard && plan.state_version !== s.dashboard.state.state_version)
      return t('经营数据刚变了，这份方案要重新比价。')
    return ''
  })
  /** "换一家" was opened while the adopted plan still waits: it can be confirmed after all. */
  const canReturnToConfirm = computed(
    () =>
      revisiting.value &&
      flow.value.stage === 'confirm' &&
      detail.value?.plan_status === 'PENDING_APPROVAL',
  )

  function remember(caseId: string, supplierId: string) {
    const list = [...new Set([...(stored.value[caseId] || []), supplierId])]
    stored.value = { ...stored.value, [caseId]: list }
    try {
      sessionStorage.setItem(EXCLUDED + caseId, JSON.stringify(list))
    } catch {}
  }
  function recall(caseId: string) {
    if (caseId in stored.value) return
    let list: string[] = []
    try {
      const value = sessionStorage.getItem(EXCLUDED + caseId)
      if (value) {
        // One supplier per Case was kept as plain text before the list.
        const parsed: unknown = value.startsWith('[') ? JSON.parse(value) : [value]
        if (Array.isArray(parsed)) list = parsed.filter((x): x is string => typeof x === 'string')
      }
    } catch {}
    stored.value = { ...stored.value, [caseId]: list }
  }

  /** Seven days of demand dated from the shop's clock, as the solver requires. */
  function dated(values: number[]) {
    const clock = s.dashboard?.state.simulation_time
    if (!clock) return null
    const dates = settlements(clock)
    return values.map((demand_qty, i) => ({ settlement_at: dates[i]!, demand_qty }))
  }
  /** A revision's scenario demand re-dated to the current clock; a forecast stays the backend's. */
  function redated(value: RecoveryCase) {
    const daily = value.daily_demand ? dated(value.daily_demand.map((d) => d.demand_qty)) : null
    return daily ? { daily_demand: daily } : {}
  }
  /** No daily forecast to compare on: the mission's demand assumption, day by day, instead. */
  function assumedDemand(value: RecoveryCase) {
    const missing = ['DAILY_DEMAND_REQUIRED', 'FORECAST_UNAVAILABLE']
    if (value.daily_demand || !value.missing_inputs.some((code) => missing.includes(code)))
      return {}
    const daily = dated(
      demandFrom({ plan: shop.plan.value, remainingDemand: shop.stock.value?.remaining_demand })
        .values,
    )
    return daily ? { daily_demand: daily } : {}
  }
  /**
   * Offers to compare, cheapest first and at most three (the solver's limit), without the excluded
   * suppliers. Null lets the backend compare every offer on file.
   */
  function suppliersFor(exclude: ReadonlySet<string>) {
    const sku = shop.mission.value?.sku_id
    const offers = (s.catalog?.offers || []).filter(
      (o) => o.sku_id === sku && !exclude.has(o.supplier_id),
    )
    if (!offers.length || (!exclude.size && offers.length <= 3)) return null
    return [...offers]
      .sort(
        (a, b) =>
          a.unit_price_minor - b.unit_price_minor || a.supplier_id.localeCompare(b.supplier_id),
      )
      .slice(0, 3)
      .map((o) => o.supplier_id)
  }
  const fail = (e: unknown) => {
    problem.value = {
      code: e instanceof ApiFailure ? e.code : '',
      message: (e as Error).message,
    }
  }
  async function run<T>(name: string, fn: () => Promise<T>) {
    if (working.value) return undefined
    working.value = name
    problem.value = null
    try {
      return await fn()
    } catch (e) {
      fail(e)
      return undefined
    } finally {
      working.value = ''
    }
  }

  /** Open the brief for a request, unless a restock of this mission is already under way. */
  async function open(request: RecoveryLaunch) {
    focus.value++
    if (inProgress.value) return false
    previousCase = detail.value?.id || ''
    if (!recovery.newDraft()) return false
    brief.value = request
    problem.value = null
    const store = s.storeId,
      sku = shop.mission.value?.sku_id
    forecast.value = null
    if (store && sku)
      api<ForecastCurrent>(
        `/api/v1/stores/${encodeURIComponent(store)}/forecast` + query({ sku_id: sku }),
      )
        .then((value) => {
          if (brief.value === request) forecast.value = value
        })
        .catch(() => {})
    await directory.load()
    // Demo mode keeps the sample documents ready: the brief only says how many are on file.
    if (
      demo.enabled.value &&
      operator.value &&
      s.session?.sourcing &&
      sku &&
      !directory.readable.value.length
    )
      await directory.loadSample(sku).catch(() => {})
    return true
  }
  function close() {
    brief.value = null
    if (previousCase) void recovery.load(previousCase)
  }

  /** Confirm the brief: create and analyze the Case, then let reviewers read the suppliers. */
  async function begin(input: { objective: string; budgetMinor: number; demand: DemandPlan }) {
    const request = brief.value
    if (!request) return
    await run('start', async () => {
      const exclude = request.exclude || ''
      const body: Record<string, unknown> = {
        objective: input.objective.trim(),
        budget_minor: input.budgetMinor,
        max_purchase_qty: null,
        supplier_ids: suppliersFor(new Set(exclude ? [exclude] : [])),
      }
      if (input.demand.source !== 'forecast') {
        const daily = dated(input.demand.values)
        if (!daily) throw new Error('经营时钟还没有同步，稍后再试。')
        body.daily_demand = daily
      }
      await recovery.start(body)
      const created = detail.value
      if (!created || created.mission_id !== missionId()) return
      brief.value = null
      if (exclude) remember(created.id, exclude)
      if (s.session?.sourcing && directory.readable.value.length) await source()
    })
  }
  /** Reviewers read every supplier on file; the Case shows their cards as they finish. */
  async function source() {
    const value = detail.value
    if (!value) return
    try {
      recovery.apply(
        await api<RecoveryCase>(
          `/api/v1/operations-cases/${encodeURIComponent(value.id)}/source`,
          'POST',
          { expected_revision: value.current_revision, district: SAMPLE_DISTRICT },
        ),
      )
    } catch (e) {
      fail(e)
      if (e instanceof ApiFailure && e.code === 'CASE_REVISION_CONFLICT')
        await recovery.load(value.id)
    }
  }
  const resource = () => run('source', source)

  /**
   * Compare again on the current facts: the clock moved, the comparison expired, a check replaced
   * the plan, or a purchase failed. Every supplier left out stays out; without a daily forecast
   * the mission's demand assumption is used, so the same failure does not come back.
   */
  async function again() {
    const value = detail.value
    if (!value) return
    await run('again', async () => {
      const changes: Record<string, unknown> = { ...redated(value), ...assumedDemand(value) }
      const reason = flow.value.again
      const supplier =
        action.value?.purchase_snapshot.supplier_id ??
        purchases.value.find((p) => p.current)?.supplierId
      if (
        supplier &&
        (reason === 'declined' ||
          reason === 'withdrawn' ||
          reason === 'short' ||
          reason === 'failed')
      )
        remember(value.id, supplier)
      const ids = suppliersFor(excludedIds.value)
      if (ids) changes.supplier_ids = ids
      await recovery.revise(changes)
    })
  }
  // The page's approval dialog is opened by the card that stays mounted (RecoveryFlow); a stage
  // component may already be gone when an adoption finishes.
  let confirmer: (() => void) | null = null
  function onConfirm(fn: () => void) {
    confirmer = fn
  }
  /** Open the approval dialog for the Case's pending plan. */
  function confirm() {
    if (approver.value) confirmer?.()
  }
  /**
   * Adopt one quote: a pending plan is written, and the approval dialog opens right away for an
   * owner who may approve. Without that role the plan waits for someone who has it (two steps).
   */
  async function adopt(candidate: RecoveryCandidate) {
    const ready = await run('adopt', async () => {
      // "换一家" after a quote was adopted from this comparison: adopting raised the mission's
      // version, so the comparison is made again first (the waiting plan is set aside) and the
      // same quote adopted from the new one. When it is gone the owner picks again.
      if (adoptedHere()) {
        await reanalyze()
        const fresh = detail.value?.proposal?.candidates.find(
          (c) =>
            c.supplier_id === candidate.supplier_id &&
            c.quantity === candidate.quantity &&
            c.feasible &&
            c.executable,
        )
        if (!fresh) return false
        candidate = fresh
      }
      let value = await recovery.materialize(candidate)
      // A routine check renewed the mission's current plan meanwhile; the Case has been read
      // again, so the same quote is adopted once more against the current plan.
      if (
        !value &&
        recovery.errorCode.value === 'PLAN_VERSION_CONFLICT' &&
        detail.value?.proposal?.candidates.some(
          (c) =>
            c.id === candidate.id &&
            c.supplier_id === candidate.supplier_id &&
            c.quantity === candidate.quantity,
        ) &&
        !detail.value.stale
      )
        value = await recovery.materialize(candidate)
      if (!value?.plan_id) return false
      revisiting.value = false
      await shop.refresh(true)
      return shop.plan.value?.id === value.plan_id && shop.canDecide.value
    })
    if (ready) confirm()
    return !!ready
  }
  /** Back from the other quotes to the adopted plan, while it still waits for confirmation. */
  function backToConfirm() {
    if (canReturnToConfirm.value) revisiting.value = false
  }
  /** A quote was adopted from the current comparison (its plan may still wait). */
  const adoptedHere = () =>
    !!detail.value?.plan_id && detail.value.plan_revision === detail.value.current_revision
  /** Compare again on the current facts, without the suppliers left out. */
  async function reanalyze() {
    const value = detail.value
    if (!value) return
    const ids = suppliersFor(excludedIds.value)
    await recovery.revise({
      ...redated(value),
      ...assumedDemand(value),
      ...(ids ? { supplier_ids: ids } : {}),
    })
  }
  const wait = () =>
    run('wait', async () => {
      // Waiting after "换一家" needs a comparison the adopted plan did not consume either.
      if (adoptedHere()) {
        await reanalyze()
        if (recovery.error.value) return
      }
      await recovery.control('adopt_waiting')
    })
  /** Take the quantity the supplier confirmed (only it is paid for); the rest is found next. */
  async function acceptPartial() {
    const value = detail.value,
      order = action.value
    if (!value || !order) return
    await run('accept', async () => {
      await shop.acceptPartialSupply(order.id)
      await recovery.load(value.id)
    })
  }

  /** The step that is waiting to be confirmed, as the owner knows it. */
  const unconfirmedStep = computed(() => {
    const request = recovery.pending.value
    if (!request) return ''
    if (request.phase === 'create') return '建立这次应急补货'
    if (request.phase === 'materialize') return '采用这份报价'
    if (request.phase === 'revise' || request.phase === 'refresh') return '重新比价'
    if (request.phase === 'analyze') return '比价'
    if (request.phase === 'source') return '找货'
    if (request.body.operation === 'cancel') return '结束这次应急补货'
    if (request.body.operation === 'adopt_waiting')
      return hasOriginals.value ? '就等原订单' : '这次不补'
    return '上一步'
  })
  /** Send it again, then carry on as that step would have when it first succeeded. */
  async function retry() {
    const request = recovery.pending.value
    if (!request) return
    const exclude = brief.value?.exclude || ''
    await run('retry', async () => {
      const value = await recovery.retry()
      if (request.phase === 'create') {
        const created = detail.value
        if (!created || created.mission_id !== missionId()) return
        brief.value = null
        if (exclude) remember(created.id, exclude)
        if (s.session?.sourcing && directory.readable.value.length) await source()
      } else if (request.phase === 'materialize' && value?.plan_id) {
        revisiting.value = false
        await shop.refresh(true)
        if (shop.plan.value?.id === value.plan_id && shop.canDecide.value) confirm()
      }
    })
  }
  const stop = () => run('stop', () => recovery.control('cancel'))
  /** A supplier offers only part of the order: take it back and compare the others. */
  async function withdrawAndSwitch() {
    const value = detail.value,
      order = action.value
    if (!value || !order) return
    await run('switch', async () => {
      await shop.withdrawOrder(order.id)
      remember(value.id, order.purchase_snapshot.supplier_id)
      await recovery.load(value.id)
      const ids = suppliersFor(excludedIds.value)
      await recovery.revise({
        ...redated(detail.value || value),
        ...(ids ? { supplier_ids: ids } : {}),
      })
    })
  }
  /** Take back an unanswered order; the Case then compares again without that supplier. */
  const withdraw = () =>
    run('withdraw', async () => {
      if (action.value) await shop.withdrawOrder(action.value.id)
    })
  const reply = (text: string) =>
    run('reply', async () => {
      if (!action.value) return null
      return shop.recordSupplierReply(action.value.id, text)
    })
  /** Goods of the Case's current order arrived (the receiving step). */
  const arrive = (quantity: number) =>
    run('arrive', async () => {
      if (!action.value) return null
      const value = await shop.recordArrival(action.value.id, quantity)
      if (detail.value) await recovery.load(detail.value.id)
      return value
    })
  /**
   * Goods of any purchase of this Case arrived. A failure is thrown to the caller, which shows it
   * where the owner recorded. Before calling, `purchases` says whether this ends the restock.
   */
  async function recordArrival(actionId: string, quantity: number) {
    if (working.value) throw new Error('请等待当前操作完成')
    working.value = 'arrive'
    problem.value = null
    try {
      await shop.recordArrival(actionId, quantity)
      if (detail.value) await recovery.load(detail.value.id)
    } finally {
      working.value = ''
    }
  }

  let slowTimer: ReturnType<typeof setTimeout> | undefined
  watch(working, (value) => {
    clearTimeout(slowTimer)
    slow.value = false
    if (value) slowTimer = setTimeout(() => (slow.value = true), SLOW_CALL_MS)
  })
  // A sourcing run that ends brings new offers into the catalog and the suppliers' names.
  watch(
    () => sourcing.value?.status,
    async (status, before) => {
      if (sourcing.value) directory.learn(sourcing.value.suppliers)
      if (before === 'running' && status && status !== 'running') await shop.refresh(true)
    },
  )
  // An excluded supplier read again by the reviewers is taken out of the comparison.
  watch(
    () => [detail.value?.id, detail.value?.current_revision, sourcing.value?.status] as const,
    async ([id]) => {
      if (!id) return
      recall(id)
      const value = detail.value!,
        left = excludedIds.value
      if (!left.size || working.value || recovery.busy.value || recovery.pending.value) return
      if (sourcing.value?.status === 'running' || value.status !== 'OPTIONS_READY') return
      const ids = value.supplier_ids || null
      if (!ids?.some((other) => left.has(other))) return
      const rest = ids.filter((other) => !left.has(other))
      if (rest.length)
        await run('exclude', () => recovery.revise({ ...redated(value), supplier_ids: rest }))
    },
  )
  watch(
    () => detail.value?.plan_id,
    async (id) => {
      if (!id || planDoc.value?.id === id) return
      try {
        const value = await api<PlanDocument>('/api/v1/plans/' + encodeURIComponent(id))
        if (detail.value?.plan_id === id) planDoc.value = value
      } catch {}
    },
    { immediate: true },
  )
  // The Case names an order the shop has not listed yet: read the shop's orders again.
  watch(
    () => !!detail.value?.action_id && !action.value,
    (missing) => {
      if (missing) void shop.refresh()
    },
  )
  // The page's dialog decided this Case's plan: read the Case now, not at the next poll, so the
  // card moves on to the order at once.
  watch(
    () => shop.s.decided,
    (decided) => {
      const value = detail.value
      if (decided && value && decided.planId === value.plan_id) void recovery.load(value.id)
    },
  )
  watch(inProgress, (value) => launcher.report(missionId(), value), { immediate: true })
  // While under way the card holds every purchase of the Case (its arrivals are recorded here,
  // where the card can say when recording ends the restock), and the plan and the order it shows.
  watch(
    () =>
      inProgress.value && detail.value
        ? JSON.stringify([
            detail.value.plan_id || null,
            ['order', 'receive'].includes(flow.value.stage) ? action.value?.id || null : null,
            purchases.value.map((p) => p.actionId),
          ])
        : '',
    (key) => {
      if (!key) return launcher.own(missionId(), null)
      const [planId, actionId, actionIds] = JSON.parse(key) as [
        string | null,
        string | null,
        string[],
      ]
      launcher.own(missionId(), { planId, actionId, actionIds })
    },
    { immediate: true },
  )
  watch(
    () => flow.value.stage,
    (stage) => {
      if (stage !== 'confirm') revisiting.value = false
    },
  )
  watch(
    () => launcher.state.value.request,
    () => {
      if (!loaded.value) return
      const request = launcher.take(missionId())
      if (request) void open(request)
    },
  )

  // While the system works on the Case it is read every two seconds, otherwise every six.
  let timer: ReturnType<typeof setInterval> | undefined
  let lastRead = 0
  async function tick() {
    const value = detail.value
    if (!value || brief.value || working.value) return
    if (recovery.busy.value || recovery.pending.value || recovery.revoked.value) return
    const state = flow.value
    const fast =
      sourcing.value?.status === 'running' ||
      (value.expert_analysis as { status?: string } | null)?.status === 'running' ||
      settling.value ||
      (state.actor === 'system' && state.stage !== 'receive')
    if (state.ended && !fast) return
    if (!fast && Date.now() - lastRead < POLL_SLOW_MS) return
    lastRead = Date.now()
    await recovery.load(value.id)
  }
  onMounted(async () => {
    await recovery.load()
    // The first state shown is a complete one: the Case's order is in the shop's list too.
    if (detail.value?.action_id && !action.value) await shop.refresh(true)
    lastRead = Date.now()
    loaded.value = true
    void directory.load()
    const request = launcher.take(missionId())
    if (request) await open(request)
    timer = setInterval(() => void tick(), POLL_FAST_MS)
  })
  onUnmounted(() => {
    clearInterval(timer)
    clearTimeout(slowTimer)
    launcher.report(missionId(), false)
    launcher.own(missionId(), null)
  })

  return {
    recovery,
    detail,
    brief,
    forecast,
    working,
    problem,
    focus,
    revisiting,
    loaded,
    operator,
    approver,
    action,
    inbound,
    originals,
    hasOriginals,
    hasBought,
    purchases,
    flow,
    actor,
    settling,
    sourcing,
    proposal,
    cmp,
    excludedIds,
    isExcluded,
    casePlan,
    planDoc,
    inProgress,
    directory,
    channel,
    channelFor,
    partial,
    againDetail,
    canConfirm,
    unavailableReason,
    canReturnToConfirm,
    open,
    close,
    begin,
    resource,
    again,
    adopt,
    confirm,
    onConfirm,
    backToConfirm,
    wait,
    stop,
    unconfirmed,
    unconfirmedStep,
    retry,
    acceptPartial,
    withdrawAndSwitch,
    withdraw,
    reply,
    arrive,
    recordArrival,
  }
}

export type RecoveryFlow = ReturnType<typeof useRecoveryFlow>
export const recoveryFlowKey: InjectionKey<RecoveryFlow> = Symbol('recovery-flow')
/** The flow of the card this component sits in. */
export function useFlow() {
  const flow = inject(recoveryFlowKey)
  if (!flow) throw new Error('Recovery flow is not provided')
  return flow
}
