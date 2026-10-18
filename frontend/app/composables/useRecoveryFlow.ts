import type { InjectionKey } from 'vue'
import { api, ApiFailure, query } from '~/utils/api'
import type { PlanDocument } from '~/types/models'
import type { ForecastCurrent } from '~/types/forecast'
import type { RecoveryCandidate, RecoveryCase, Sourcing } from '~/types/recovery'
import {
  comparison,
  flowState,
  settlements,
  type DemandPlan,
  type RecoveryLaunch,
} from '~/utils/recovery'
import { SAMPLE_DISTRICT } from '~/composables/useSupplierDirectory'

// The emergency restock flow of one mission (workspace §18). It drives the recovery Case through
// the existing endpoints: create and analyze, source, materialize, wait, cancel; the purchase
// itself is confirmed in the page's approval dialog and its order handled by the shop's own
// commands. Nothing here approves a purchase on its own.

const EXCLUDED = 'ss.recovery.excluded:'

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
  /** A step this page is running between backend calls ("系统在做"). */
  const working = ref('')
  /** The last failure of a call made here (sourcing, withdrawal, reply, arrival). */
  const problem = ref<{ code: string; message: string } | null>(null)
  /** Bumped when a request asks the flow to be looked at; the card scrolls into view. */
  const focus = ref(0)
  /** The owner looks at the other quotes again while an adopted plan waits ("换一家"). */
  const revisiting = ref(false)
  const loaded = ref(false)
  let previousCase = ''

  const operator = computed(() => shop.hasRole('operator'))
  const approver = computed(() => shop.hasRole('approver'))
  const action = computed(
    () =>
      (detail.value?.action_id && s.actions.find((a) => a.id === detail.value!.action_id)) || null,
  )
  const inbound = computed(
    () => (action.value && s.inbounds.find((i) => i.action_id === action.value!.id)) || null,
  )
  /** Original orders the analysis counted on, still tracked by the shop. */
  const originals = computed(() => {
    const ids = new Set(
      (detail.value?.evidence || []).filter((e) => e.kind === 'inbound_order').map((e) => e.id),
    )
    return s.inbounds.filter((i) => ids.has(i.action_id))
  })
  const flow = computed(() =>
    flowState({
      detail: brief.value ? null : detail.value,
      action: brief.value ? null : action.value,
      inbound: inbound.value,
      originals: originals.value,
    }),
  )
  const sourcing = computed(() => (detail.value?.sourcing as Sourcing | null | undefined) || null)
  const proposal = computed(() => detail.value?.proposal || null)
  /** Excluded suppliers per Case: one that declined, or whose order was taken back. */
  const excludes = ref<Record<string, string>>({})
  const excluded = computed(() =>
    brief.value
      ? brief.value.exclude || ''
      : detail.value
        ? excludes.value[detail.value.id] || ''
        : '',
  )
  const cmp = computed(() => {
    const value = comparison(proposal.value)
    return excluded.value
      ? { ...value, options: value.options.filter((o) => o.supplierId !== excluded.value) }
      : value
  })
  /** The Case's plan: the shop's current plan while it waits, otherwise the stored document. */
  const casePlan = computed(() =>
    detail.value?.plan_id && shop.plan.value?.id === detail.value.plan_id
      ? shop.plan.value
      : planDoc.value?.id === detail.value?.plan_id
        ? planDoc.value
        : null,
  )
  const inProgress = computed(() => !!brief.value || (!!detail.value && !flow.value.ended))

  function remember(caseId: string, supplierId: string) {
    excludes.value = { ...excludes.value, [caseId]: supplierId }
    try {
      sessionStorage.setItem(EXCLUDED + caseId, supplierId)
    } catch {}
  }
  function recall(caseId: string) {
    if (caseId in excludes.value) return
    try {
      const value = sessionStorage.getItem(EXCLUDED + caseId)
      if (value) excludes.value = { ...excludes.value, [caseId]: value }
    } catch {}
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
  /**
   * Offers to compare, cheapest first and at most three (the solver's limit), without the excluded
   * supplier. Null lets the backend compare every offer on file.
   */
  function suppliersFor(exclude: string) {
    const sku = shop.mission.value?.sku_id
    const offers = (s.catalog?.offers || []).filter(
      (o) => o.sku_id === sku && o.supplier_id !== exclude,
    )
    if (!offers.length || (!exclude && offers.length <= 3)) return null
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
        supplier_ids: suppliersFor(exclude),
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
   * the plan, or the purchase failed. A supplier that declined is left out.
   */
  async function again() {
    const value = detail.value
    if (!value) return
    await run('again', async () => {
      const changes: Record<string, unknown> = redated(value)
      const reason = flow.value.again
      const supplier = action.value?.purchase_snapshot.supplier_id
      if ((reason === 'declined' || reason === 'withdrawn') && supplier) {
        remember(value.id, supplier)
        const ids = suppliersFor(supplier)
        if (ids) changes.supplier_ids = ids
      }
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
      const value = await recovery.materialize(candidate)
      if (!value?.plan_id) return false
      revisiting.value = false
      await shop.refresh(true)
      return shop.plan.value?.id === value.plan_id && shop.canDecide.value
    })
    if (ready) confirm()
    return !!ready
  }
  const wait = () => run('wait', () => recovery.control('adopt_waiting'))

  /**
   * A submission whose answer never came back (a 5xx or a dropped connection) may or may not have
   * taken effect, so nothing else writes until it is sent again under its original key; the
   * backend then answers with what it did the first time.
   */
  const unconfirmed = computed(() => !!recovery.pending.value)
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
      return originals.value.length ? '就等原订单' : '这次不补'
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
      const supplier = order.purchase_snapshot.supplier_id
      remember(value.id, supplier)
      await recovery.load(value.id)
      const ids = suppliersFor(supplier)
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
  const arrive = (quantity: number) =>
    run('arrive', async () => {
      if (!action.value) return null
      return shop.recordArrival(action.value.id, quantity)
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
        supplier = excludes.value[id]
      if (!supplier || working.value || recovery.busy.value || recovery.pending.value) return
      if (sourcing.value?.status === 'running' || value.status !== 'OPTIONS_READY') return
      const ids = value.supplier_ids || null
      if (!ids?.includes(supplier)) return
      const rest = ids.filter((other) => other !== supplier)
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
  watch(inProgress, (value) => launcher.report(missionId(), value), { immediate: true })
  // The plan this restock adopted ran out or a regular check replaced it: the page's regular
  // plan line then says so instead of quietly showing the plan that took its place.
  const lapsed = computed(() => ['expired', 'superseded'].includes(flow.value.again || ''))
  watch(
    () =>
      inProgress.value && detail.value
        ? `${detail.value.plan_id || ''}|${detail.value.action_id || ''}|${lapsed.value ? 1 : ''}`
        : '',
    (key) => {
      const [planId, actionId, gone] = key.split('|')
      launcher.own(
        missionId(),
        key ? { planId: planId || null, actionId: actionId || null, lapsed: !!gone } : null,
      )
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

  // While the system works the Case is read every two seconds, otherwise every six.
  let timer: ReturnType<typeof setInterval> | undefined
  let ticks = 0
  async function tick() {
    ticks++
    const value = detail.value
    if (!value || brief.value || working.value) return
    if (recovery.busy.value || recovery.pending.value || recovery.revoked.value) return
    const fast =
      sourcing.value?.status === 'running' ||
      (value.expert_analysis as { status?: string } | null)?.status === 'running' ||
      flow.value.actor === 'system'
    if (flow.value.ended && !fast) return
    if (fast || ticks % 3 === 0) await recovery.load(value.id)
  }
  onMounted(async () => {
    await recovery.load()
    loaded.value = true
    void directory.load()
    const request = launcher.take(missionId())
    if (request) await open(request)
    timer = setInterval(() => void tick(), 2000)
  })
  onUnmounted(() => {
    clearInterval(timer)
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
    flow,
    sourcing,
    proposal,
    cmp,
    excluded,
    casePlan,
    planDoc,
    inProgress,
    directory,
    open,
    close,
    begin,
    resource,
    again,
    adopt,
    confirm,
    onConfirm,
    wait,
    stop,
    unconfirmed,
    unconfirmedStep,
    retry,
    withdrawAndSwitch,
    withdraw,
    reply,
    arrive,
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
