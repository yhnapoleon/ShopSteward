import { t } from '~/i18n'
import type { Schema, Session, PendingApproval, PlanDocument } from '~/types/models'
import { isRecoveryPlan, selectedPlanCandidate } from '~/utils/plans'
import { api, query, ApiFailure } from '~/utils/api'
import { productDisplayName, rememberSupplierNames, supplierDisplayName } from '~/utils/glossary'
import {
  DIRECTORY_STATE,
  emptyDirectory,
  fetchDirectory,
  type DirectoryState,
} from '~/composables/useSupplierDirectory'

/**
 * A write to an order (supplier reply, withdrawal, partial acceptance, arrival) whose answer has
 * not come back. `mark` is the order as it stood when the write went out: while the order still
 * reads the same, the write may or may not have taken effect, and the same write is sent again
 * under its first key, so the backend answers with what it did the first time and nothing counts
 * twice. Once the order reads differently, the write (or another) took effect and is let go.
 */
type OrderWrite = {
  storeId: string
  actionId: string
  path: string
  body: Record<string, unknown>
  key: string
  mark: string
}
const ORDER_WRITES = 'ss.order-writes'
/** Names this page gave suppliers that have none on file, so a later real name can replace them. */
const fallbackNames = new Map<string, string>()

export function useShop() {
  const s = useState('shop', () => ({
    session: null as Session | null,
    stores: [] as Schema<'StoreSummary'>[],
    storeId: '',
    activeStoreId: '',
    discovering: false,
    missionId: '',
    requestedMissionId: '',
    planChange: null as { from: PlanDocument; to: PlanDocument } | null,
    dashboard: null as Schema<'Dashboard'> | null,
    catalog: null as Schema<'Catalog'> | null,
    missions: [] as Schema<'Mission'>[],
    plan: null as PlanDocument | null,
    actions: [] as Schema<'Action'>[],
    inbounds: [] as Schema<'InboundItem'>[],
    timeline: [] as Schema<'TimelineEntry'>[],
    timelineCursor: null as string | null,
    ledger: [] as Schema<'LedgerEntryView'>[],
    ledgerCursor: null as string | null,
    alerts: [] as Schema<'Alert'>[],
    selected: 0,
    busy: '',
    loading: true,
    refreshing: false,
    error: '',
    connected: false,
    notice: '',
    requestSeq: 0,
    storeVersion: 0,
    pending: null as PendingApproval | null,
    /** The last plan decided here (an emergency restock reads its Case again at once). */
    decided: null as { planId: string; at: number } | null,
    /** Order writes whose answer has not come back, by request path. */
    orderWrites: {} as Record<string, OrderWrite>,
    runs: {} as Record<string, string>,
  })).value
  const directory = useState<DirectoryState>(DIRECTORY_STATE, emptyDirectory)
  const launcher = useRecoveryLaunch()
  const mission = computed(() => s.missions.find((m) => m.id === s.missionId) || null)
  const stock = computed(
    () =>
      s.dashboard?.state.stocks.find((x) => x.sku_id === mission.value?.sku_id) ||
      s.dashboard?.state.stocks[0],
  )
  // The product as the pages name it: the catalog entry with its display name (glossary).
  const product = computed(() => {
    const found = s.catalog?.products.find((x) => x.sku_id === stock.value?.sku_id)
    return found && { ...found, name: productDisplayName(found) }
  })
  const offer = computed(() => s.catalog?.offers.find((x) => x.sku_id === stock.value?.sku_id))
  const plan = computed(() => s.plan)
  const unresolved = computed(() =>
    s.actions.find((a) => ['QUEUED', 'EXECUTING', 'UNKNOWN'].includes(a.status)),
  )
  // Sent by the owner and not yet answered: nothing is retried, the order simply waits.
  const awaitingSupplier = computed(() =>
    unresolved.value?.channel === 'assisted' && unresolved.value.status === 'EXECUTING'
      ? unresolved.value
      : null,
  )
  // Confirmed, but no source reports the goods of an order sent by hand: the owner records them.
  const arrivalsToRecord = computed(() =>
    s.actions.flatMap((action) => {
      const inbound = s.inbounds.find((i) => i.action_id === action.id)
      return action.channel === 'assisted' &&
        action.status === 'SUCCEEDED' &&
        action.mission_id === s.missionId &&
        inbound &&
        inbound.remaining_quantity > 0
        ? [{ action, inbound }]
        : []
    }),
  )
  // The ones the page's arrival card records. An emergency restock under way records its own
  // purchases in its card, which says when recording one would end the restock (recording the
  // last of them settles it), so they are not offered a second time elsewhere.
  const awaitingArrival = computed(() =>
    arrivalsToRecord.value.filter(({ action }) => !launcher.holds(action.mission_id, action.id)),
  )
  const currentCandidate = computed(() => selectedPlanCandidate(s.plan, s.selected))
  const canDecide = computed(
    () =>
      s.connected &&
      !s.pending &&
      !unresolved.value &&
      mission.value?.status === 'ACTIVE' &&
      s.plan?.status === 'PENDING_APPROVAL' &&
      Boolean(s.plan.proposed_purchase) &&
      s.dashboard?.freshness.status === 'FRESH' &&
      s.plan.state_version === s.dashboard.state.state_version &&
      Date.parse(s.plan.expires_at) > Date.now(),
  )
  const hasRole = (role: string) =>
    Boolean(s.session?.roles.includes(role) || s.session?.roles.includes('admin'))
  const notify = (message: string) => {
    s.notice = message
  }
  async function init(preferredStore?: string) {
    s.loading = true
    try {
      s.session = await $fetch<Session>('/api/session')
      if (!s.session.authenticated) {
        s.loading = false
        return
      }
      const list = await api<Schema<'StoreList'>>('/api/v1/stores?limit=100')
      applyStores(list)
      try {
        s.runs = JSON.parse(localStorage.getItem('ss.scenarios') || '{}')
        const pending = JSON.parse(sessionStorage.getItem('ss.approval') || 'null')
        if (pending?.key && pending?.body) s.pending = pending
        const writes = JSON.parse(sessionStorage.getItem(ORDER_WRITES) || '{}')
        if (writes && typeof writes === 'object') s.orderWrites = writes
      } catch {}
      const saved = localStorage.getItem('ss.store')
      await selectStore(
        (preferredStore && s.stores.some((st) => st.store_id === preferredStore)
          ? preferredStore
          : '') ||
          s.activeStoreId ||
          (s.stores.some((x) => x.store_id === saved) ? saved! : s.stores[0]?.store_id || ''),
      )
    } catch (e) {
      s.error = (e as Error).message
      s.connected = false
    } finally {
      s.loading = false
    }
  }
  function applyStores(list: Schema<'StoreList'>) {
    s.stores = list.items
    s.activeStoreId = list.active_store?.store_id || ''
    if (list.active_store && !s.stores.some((st) => st.store_id === s.activeStoreId))
      s.stores.unshift(list.active_store)
  }
  async function pollEnvironment() {
    if (!s.session?.authenticated || s.discovering || s.busy) return
    s.discovering = true
    try {
      const list = await api<Schema<'StoreList'>>('/api/v1/stores?limit=100')
      // A user command may have started while discovery was in flight.
      if (s.busy) return
      const previous = s.activeStoreId
      applyStores(list)
      if (s.activeStoreId && s.activeStoreId !== previous) {
        await selectStore(s.activeStoreId)
        notify('模拟器已切换经营环境，正在使用新场景的实际数据。')
      } else await refresh()
    } catch (e) {
      s.connected = false
      s.error = (e as Error).message
    } finally {
      s.discovering = false
    }
  }
  async function selectStore(id: string) {
    s.requestSeq++
    s.storeVersion++
    s.storeId = id
    s.missionId = ''
    s.requestedMissionId = ''
    s.planChange = null
    s.plan = null
    s.actions = []
    s.missions = []
    s.dashboard = null
    s.catalog = null
    s.inbounds = []
    s.timeline = []
    s.timelineCursor = null
    s.ledger = []
    s.ledgerCursor = null
    s.alerts = []
    s.error = ''
    s.connected = false
    if (id) localStorage.setItem('ss.store', id)
    await refresh(true)
  }
  async function refresh(force = false) {
    if (!s.storeId || (!force && s.refreshing)) return
    const id = s.storeId,
      seq = ++s.requestSeq
    s.refreshing = true
    // The suppliers' names are read beside the store's data, without holding it up (§6.3).
    void readDirectory(id).then(() => {
      if (id === s.storeId) nameSuppliers()
    })
    try {
      const [dashboard, catalog, missions, actions, inbounds, alerts, ledger] = await Promise.all([
        api<Schema<'Dashboard'>>('/api/v1/dashboard' + query({ store_id: id })),
        api<Schema<'Catalog'>>('/api/v1/catalog' + query({ store_id: id })),
        api<Schema<'MissionList'>>('/api/v1/missions' + query({ store_id: id, limit: 100 })),
        api<Schema<'ActionList'>>('/api/v1/actions' + query({ store_id: id, limit: 100 })),
        api<Schema<'InboundList'>>('/api/v1/inbounds' + query({ store_id: id, limit: 100 })),
        api<Schema<'AlertList'>>('/api/v1/alerts' + query({ store_id: id, limit: 100 })),
        api<Schema<'LedgerEntryList'>>(
          '/api/v1/ledger-entries' + query({ store_id: id, limit: 30 }),
        ),
      ])
      if (s.requestedMissionId && !missions.items.some((m) => m.id === s.requestedMissionId)) {
        const selected = await api<Schema<'Mission'>>(
          '/api/v1/missions/' + encodeURIComponent(s.requestedMissionId),
        )
        if (selected.store_id !== id) throw new Error('这项任务不属于当前店铺。')
        missions.items.push(selected)
      }
      const m =
        missions.items.find((x) => x.id === s.requestedMissionId) ||
        missions.items.find((x) => x.id === s.missionId) ||
        missions.items.find((x) => x.status === 'ACTIVE') ||
        missions.items[0]
      const [nextPlan, timeline] = await Promise.all([
        m?.current_plan_id
          ? api<PlanDocument>('/api/v1/plans/' + m.current_plan_id)
          : Promise.resolve(null),
        m
          ? api<Schema<'TimelineEntryList'>>('/api/v1/missions/' + m.id + '/timeline?limit=30')
          : Promise.resolve({ items: [], next_cursor: null }),
      ])
      if (seq !== s.requestSeq || id !== s.storeId) return
      const sameMission = m?.id === s.missionId
      const retained = sameMission && s.timeline.length > 30
      const combined = retained
        ? [...timeline.items, ...s.timeline].filter(
            (item, index, items) => items.findIndex((other) => other.id === item.id) === index,
          )
        : timeline.items
      if (sameMission && s.plan && nextPlan && s.plan.id !== nextPlan.id)
        s.planChange = { from: s.plan, to: nextPlan }
      if (nextPlan?.id !== s.plan?.id) s.selected = nextPlan?.proposed_purchase?.quantity || 0
      Object.assign(s, {
        dashboard,
        catalog,
        missions: missions.items,
        missionId: m?.id || '',
        plan: nextPlan,
        actions: actions.items,
        inbounds: inbounds.items,
        alerts: alerts.items,
        ledger: ledger.items,
        ledgerCursor: ledger.next_cursor,
        timeline: combined,
        timelineCursor: retained ? s.timelineCursor : timeline.next_cursor,
        connected: true,
        error: '',
      })
      if (s.pending?.storeId === id && actions.items.some((a) => a.plan_id === s.pending!.planId)) {
        s.pending = null
        sessionStorage.removeItem('ss.approval')
      }
      settleOrderWrites(id)
      nameSuppliers()
    } catch (e) {
      if (seq === s.requestSeq) {
        s.connected = false
        s.error = (e as Error).message
      }
    } finally {
      if (seq === s.requestSeq) s.refreshing = false
    }
  }
  async function readDirectory(store: string) {
    if (!s.session?.sourcing) return
    await fetchDirectory(directory, store, () => s.storeId)
  }
  /**
   * Every supplier the page names gets a name (§6.3). One with no name on file is called by what
   * it is to this mission: its usual supplier ("原供应商", the one the original orders went to) or
   * another connected one ("已对接的供应商"). The id stays in each record's traceable details.
   * Names on file (documents, sourcing runs) always replace these.
   */
  function nameSuppliers() {
    // Until the documents are read, only the usual supplier is named; another one may still get
    // its real name from them.
    const settled = !s.session?.sourcing || directory.value.loaded || !!directory.value.error
    const usual = new Set(s.missions.map((m) => m.policy.supplier_id))
    const ids = new Set([
      ...usual,
      ...(s.catalog?.offers || []).map((o) => o.supplier_id),
      ...s.actions.map((a) => a.purchase_snapshot.supplier_id),
    ])
    const entries: { supplier_id: string; name: string }[] = []
    for (const id of ids) {
      if (!settled && !usual.has(id)) continue
      const label = supplierDisplayName(id)
      const number = /^supplier[_-]?(\d+)$/i.exec(id)?.[1]
      const unnamed = number ? t('供应商 {0}', [number.padStart(3, '0')]) : id
      if (label !== unnamed && label !== fallbackNames.get(id)) continue
      const name = t(usual.has(id) ? '原供应商' : '已对接的供应商')
      fallbackNames.set(id, name)
      if (label !== name) entries.push({ supplier_id: id, name })
    }
    if (entries.length) rememberSupplierNames(entries)
  }
  /** The order as it stands now, to tell whether an unconfirmed write to it took effect. */
  function orderMark(actionId: string) {
    const action = s.actions.find((a) => a.id === actionId)
    const inbound = s.inbounds.find((i) => i.action_id === actionId)
    return [
      action?.status || '',
      action?.supplier_reply?.recorded_at || '',
      inbound?.received_quantity ?? 0,
    ].join('|')
  }
  function keepWrites(next: Record<string, OrderWrite>) {
    s.orderWrites = next
    try {
      if (Object.keys(next).length) sessionStorage.setItem(ORDER_WRITES, JSON.stringify(next))
      else sessionStorage.removeItem(ORDER_WRITES)
    } catch {}
  }
  function dropWrite(path: string) {
    const { [path]: _, ...rest } = s.orderWrites
    keepWrites(rest)
  }
  /** Unconfirmed writes to orders that have changed since took effect (or were overtaken). */
  function settleOrderWrites(store: string) {
    const kept = Object.fromEntries(
      Object.entries(s.orderWrites).filter(
        ([, w]) => w.storeId !== store || orderMark(w.actionId) === w.mark,
      ),
    )
    if (Object.keys(kept).length !== Object.keys(s.orderWrites).length) keepWrites(kept)
  }
  /**
   * One write to an order, safe to repeat: while an earlier attempt is unconfirmed, the same
   * write goes out under the earlier key; a different one waits until that is settled.
   */
  async function orderWrite(
    name: string,
    actionId: string,
    segment: 'supplier-reply' | 'withdrawal' | 'partial-acceptance' | 'arrival',
    body: Record<string, unknown>,
  ) {
    return command(name, async () => {
      const path = '/api/v1/actions/' + encodeURIComponent(actionId) + '/' + segment
      const held = s.orderWrites[path]?.storeId === s.storeId ? s.orderWrites[path] : undefined
      const same = !!held && JSON.stringify(held.body) === JSON.stringify(body)
      if (held && !same)
        throw new Error(
          segment === 'arrival'
            ? '上一次登记到货的结果还没确认；先按上次的件数再登记一次核实，不会重复入账。'
            : '上一次提交的结果还没确认；先按原来的内容再提交一次核实，不会重复。',
        )
      const write: OrderWrite =
        held && same
          ? held
          : {
              storeId: s.storeId,
              actionId,
              path,
              body,
              key: crypto.randomUUID(),
              mark: orderMark(actionId),
            }
      keepWrites({ ...s.orderWrites, [path]: write })
      try {
        const value = await api<Schema<'Action'>>(path, 'POST', body, write.key)
        dropWrite(path)
        return value
      } catch (e) {
        // Refused outright: it did not take effect. A lost answer or a 5xx may have.
        if (e instanceof ApiFailure && e.status >= 400 && e.status < 500) dropWrite(path)
        throw e
      } finally {
        await refresh(true)
      }
    })
  }
  async function command<T>(name: string, fn: () => Promise<T>) {
    if (s.busy) throw new Error('请等待当前操作完成')
    s.busy = name
    try {
      return await fn()
    } catch (e) {
      s.error = (e as Error).message
      throw e
    } finally {
      s.busy = ''
    }
  }
  async function waitJob(id: string) {
    for (let i = 0; i < 60; i++) {
      const job = await api<Schema<'JobRun'>>('/api/v1/job-runs/' + id)
      if (job.status === 'SUCCEEDED') return job
      if (['FAILED', 'CANCELLED'].includes(job.status))
        throw new Error(job.last_error || '后台任务未完成')
      await new Promise((r) => setTimeout(r, 500))
    }
    throw new Error('后台仍在处理，请稍后刷新；不会重复创建任务。')
  }
  async function createScenario() {
    return command('正在创建示例店铺', async () => {
      const accepted = await api<Schema<'ScenarioAccepted'>>('/dev/v1/scenarios', 'POST', {
        scenario: 'SC01',
      })
      const job = await waitJob(accepted.job_run_id)
      const id = job.result?.references.find((r) => r.type === 'store')?.id,
        run = job.result?.references.find((r) => r.type === 'scenario')?.id
      if (!id || !run) throw new Error('初始化回执缺少店铺或场景引用')
      s.runs[id] = run
      localStorage.setItem('ss.scenarios', JSON.stringify(s.runs))
      applyStores(await api<Schema<'StoreList'>>('/api/v1/stores?limit=100'))
      await selectStore(s.activeStoreId || id)
      notify(
        s.storeId === id
          ? '新示例店铺已准备好，尚未采购。'
          : '场景已创建，当前正在使用随后创建的最新经营环境。',
      )
    })
  }
  async function startMission() {
    return command('正在建立备货委托', async () => {
      if (!s.storeId || !stock.value || !offer.value) throw new Error('请先选择具有完整资料的店铺')
      const existing = s.missions.find(
        (m) => m.sku_id === stock.value?.sku_id && ['ACTIVE', 'PAUSED'].includes(m.status),
      )
      if (existing) {
        await selectMission(existing.id)
        return
      }
      const body: Schema<'MissionCreate'> = {
        store_id: s.storeId,
        sku_id: stock.value.sku_id,
        objective: '活动备货：尽量减少缺货，现金至少保留300元，采购逐笔确认。',
        policy: {
          cash_floor_minor: 30000,
          candidate_quantities: [0, 20, 40, 80],
          supplier_id: offer.value.supplier_id,
        },
        check_interval_seconds: 30,
      }
      const m = await api<Schema<'Mission'>>('/api/v1/missions', 'POST', body)
      s.requestedMissionId = m.id
      s.missionId = m.id
      s.plan = null
      s.planChange = null
      await refresh(true)
      notify('委托已建立。')
    })
  }
  async function requestCheck() {
    return command('正在重新检查', async () => {
      if (!mission.value) return
      const j = await api<Schema<'JobAccepted'>>(
        '/api/v1/missions/' + mission.value.id + '/checks',
        'POST',
        {},
      )
      await waitJob(j.job_run_id)
      await refresh(true)
    })
  }
  async function selectMission(id: string) {
    if (s.missionId === id && s.requestedMissionId === id) return
    s.requestSeq++
    s.requestedMissionId = id
    s.missionId = id
    s.plan = null
    s.planChange = null
    s.timeline = []
    s.timelineCursor = null
    await refresh(true)
  }
  async function control(operation: 'pause' | 'resume' | 'complete') {
    return command(
      operation === 'pause' ? '正在暂停' : operation === 'complete' ? '正在结束委托' : '正在恢复',
      async () => {
        if (!mission.value) return
        await api<Schema<'Mission'>>('/api/v1/missions/' + mission.value.id + '/control', 'POST', {
          operation,
          expected_mission_version: mission.value.mission_version,
        } satisfies Schema<'MissionControl'>)
        await refresh(true)
      },
    )
  }
  async function prepareDecision() {
    return command('正在核对方案', async () => {
      if (!canDecide.value || !s.plan || !mission.value)
        throw new Error('当前方案不可确认，请刷新或重新检查。')
      if (s.selected !== 0 && s.selected !== s.plan.proposed_purchase?.quantity) {
        if (isRecoveryPlan(s.plan)) throw new Error('请在应急补货里重新选择报价，再确认。')
        if (!s.session?.planRevision)
          throw new Error(
            '当前后端尚未提供数量修订接口，可以比较候选，但本次只能确认后端推荐数量。',
          )
        const selected = s.selected
        const revised = await api<Schema<'Plan'>>(
          '/api/v1/plans/' + s.plan.id + '/revision',
          'POST',
          {
            expected_mission_version: mission.value.mission_version,
            max_purchase_qty: selected > s.plan.proposed_purchase!.quantity ? null : selected,
          } satisfies Schema<'PlanRevisionRequest'>,
        )
        s.plan = revised
        await refresh(true)
        if (s.plan?.proposed_purchase?.quantity !== selected)
          throw new Error('新方案的数量已变化，请重新查看并选择。')
        s.selected = selected
      }
      return { plan: structuredClone(toRaw(s.plan)), quantity: s.selected }
    })
  }
  async function decide(snapshot: { plan: PlanDocument; quantity: number }) {
    return command('正在提交确认', async () => {
      if (snapshot.plan.id !== s.plan?.id || snapshot.plan.mission_id !== s.missionId)
        throw new Error('经营环境或方案已经变化，请重新核对。')
      const pending: PendingApproval = {
        storeId: s.storeId,
        planId: snapshot.plan.id,
        body: {
          decision: snapshot.quantity === 0 ? 'reject' : 'approve',
          expected_plan_version: snapshot.plan.plan_version,
          expected_state_version: snapshot.plan.state_version,
          proposal_hash: snapshot.plan.proposal_hash,
        },
        key: crypto.randomUUID(),
      }
      s.pending = pending
      sessionStorage.setItem('ss.approval', JSON.stringify(pending))
      try {
        await api<Schema<'DecisionApproved'> | Schema<'DecisionRejected'>>(
          '/api/v1/plans/' + pending.planId + '/decision',
          'POST',
          pending.body,
          pending.key,
        )
        s.pending = null
        sessionStorage.removeItem('ss.approval')
        s.decided = { planId: pending.planId, at: Date.now() }
        notify(
          snapshot.quantity === 0
            ? '本轮取舍已记录，条件变化后再检查。'
            : '确认已受理，正在核实采购结果。',
        )
      } catch (e) {
        if (e instanceof ApiFailure && e.status >= 400 && e.status < 500) {
          s.pending = null
          sessionStorage.removeItem('ss.approval')
        }
        throw e
      } finally {
        await refresh(true)
      }
    })
  }
  async function recoverApproval() {
    return command('正在查询原确认结果', async () => {
      const p = s.pending
      if (!p) return
      await api('/api/v1/plans/' + p.planId + '/decision', 'POST', p.body, p.key)
      s.pending = null
      sessionStorage.removeItem('ss.approval')
      s.decided = { planId: p.planId, at: Date.now() }
      await refresh(true)
    })
  }
  // An order the owner sends by hand: the pasted reply becomes its receipt, or it keeps waiting.
  const recordSupplierReply = (actionId: string, text: string) =>
    orderWrite('正在登记供应商回复', actionId, 'supplier-reply', {
      text,
    } satisfies Schema<'SupplierReplyText'>)
  const withdrawOrder = (actionId: string) => orderWrite('正在撤回订单', actionId, 'withdrawal', {})
  // The supplier confirmed fewer units: take that quantity; the rest of the hold is released.
  const acceptPartialSupply = (actionId: string) =>
    orderWrite('正在按对方数量成交', actionId, 'partial-acceptance', {})
  const recordArrival = (actionId: string, quantity: number) =>
    orderWrite('正在登记到货', actionId, 'arrival', {
      quantity,
    } satisfies Schema<'ArrivalRecord'>)
  async function advance() {
    return command('正在推进经营事件', async () => {
      const run = s.runs[s.storeId]
      if (!run) throw new Error('此场景没有本浏览器的控制记录，请新建一轮示例。')
      const j = await api<Schema<'JobAccepted'>>('/dev/v1/scenarios/' + run + '/advance', 'POST', {
        steps: 1,
      })
      await waitJob(j.job_run_id)
      await refresh(true)
      notify('模拟器事件已推进；后台正在同步并复查。')
    })
  }
  async function acknowledge(id: string) {
    await command('正在记录知晓', async () => {
      await api('/api/v1/alerts/' + id + '/acknowledgement', 'POST', {})
      await refresh(true)
    })
  }
  async function moreTimeline() {
    if (!mission.value || !s.timelineCursor) return
    const missionId = mission.value.id,
      version = s.storeVersion
    const r = await api<Schema<'TimelineEntryList'>>(
      '/api/v1/missions/' +
        missionId +
        '/timeline' +
        query({ cursor: s.timelineCursor, limit: 30 }),
    )
    if (version !== s.storeVersion || missionId !== s.missionId) return
    s.timeline.push(...r.items)
    s.timelineCursor = r.next_cursor
  }
  return {
    s,
    mission,
    stock,
    product,
    offer,
    plan,
    unresolved,
    awaitingSupplier,
    arrivalsToRecord,
    awaitingArrival,
    currentCandidate,
    canDecide,
    hasRole,
    init,
    refresh,
    pollEnvironment,
    selectStore,
    createScenario,
    startMission,
    requestCheck,
    control,
    selectMission,
    prepareDecision,
    decide,
    recoverApproval,
    recordSupplierReply,
    withdrawOrder,
    acceptPartialSupply,
    recordArrival,
    advance,
    acknowledge,
    moreTimeline,
    notify,
  }
}
