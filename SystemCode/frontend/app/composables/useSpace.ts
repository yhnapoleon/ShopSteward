import { t } from '~/i18n'
import type { Schema } from '~/types/models'
import { firstSync, statusBadge, type Badge } from '~/utils/glossary'
import { timelineItems } from '~/utils/timeline'
import { when } from '~/utils/presentation'
import { workPresentation } from '~/utils/workPresentation'

// Derived state of the unified work-item workspace (workspace redesign §4). Every value is read
// from the existing shop / work-item / Agent state; nothing here writes business data.

type Work = Schema<'WorkView'>
const settledActions = ['SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE']

/** A mission item's own status only matters while the owner is asked or the assistant works. */
const workForBadge = (item: Work) =>
  item.mission_id
    ? ['WAITING_INPUT', 'PROCESSING'].includes(item.status)
      ? item.status
      : null
    : item.status

/** The owner has to act on this item: answer, confirm, verify or recover something. */
export function needsOwner(item: Work) {
  return (
    !!(item.business?.needs_attention || item.business?.can_confirm) ||
    ['WAITING_INPUT', 'BLOCKED'].includes(item.status)
  )
}

/** Status badge for a listed work item, from what the item itself carries (§6.2). */
export function workBadge(item: Work, now = Date.now(), ownerRecordsArrival = false): Badge {
  const business = item.business
  const code = business?.code || ''
  const expired = !!business?.valid_until && Date.parse(business.valid_until) <= now
  // Item states the vocabulary table does not name: say them in the item's own words.
  if (
    item.status === 'PROCESSING' &&
    item.processing_expires_at &&
    Date.parse(item.processing_expires_at) <= now
  )
    return { label: t('处理中断，等待恢复'), tone: 'amber' }
  if (!business && item.status === 'BLOCKED') return { label: t('需要处理'), tone: 'amber' }
  if (!business && item.status === 'RECEIVED') return { label: t('已收到'), tone: 'blue' }
  const badge = statusBadge({
    work: workForBadge(item),
    mission: item.mission?.status,
    plan: code === 'PENDING_APPROVAL' ? 'PENDING_APPROVAL' : undefined,
    canDecide: !!business?.can_confirm && !expired,
    inTransit: code === 'IN_TRANSIT' ? 1 : 0,
    ownerRecordsArrival,
    business,
  })
  // The backend says the owner is needed (stale data, a plan to re-check, another purchase
  // awaiting verification) although no vocabulary rule above matched: say so plainly.
  if (business?.needs_attention && badge.tone !== 'amber')
    return { label: t('需要处理'), tone: 'amber' }
  return badge
}

type ShopState = ReturnType<typeof useShop>['s']

/** Goods of an order the owner sent by hand are on the way: only the owner can record them. */
export const awaitsOwnerArrival = (missionId: string | null | undefined, s: ShopState) =>
  !!missionId &&
  s.actions.some(
    (a) =>
      a.mission_id === missionId &&
      a.channel === 'assisted' &&
      a.status === 'SUCCEEDED' &&
      s.inbounds.some((i) => i.action_id === a.id && i.remaining_quantity > 0),
  )

/**
 * A mission's latest change worth one line (§5): purchase orders, arrivals, the owner's own actions
 * and new reminders come first; routine checks never count. Null when nothing has happened yet.
 */
function latestChange(missionId: string, s: ShopState) {
  const items = timelineItems(s.timeline).filter((i) => !i.event.routine)
  const notable = items.find(
    (i) => i.event.icon === 'user' || ['order', 'alert'].includes(i.event.kind),
  )
  // Arrivals are not mission timeline entries; the store ledger records them per purchase order.
  const orders = new Set(s.actions.filter((a) => a.mission_id === missionId).map((a) => a.id))
  const time = (at: string | null | undefined) => Date.parse(at || '') || 0
  const arrival = s.ledger
    .filter((e) => e.effect_type === 'GOODS_RECEIVED' && !!e.action_id && orders.has(e.action_id))
    .sort((a, b) => time(b.occurred_at) - time(a.occurred_at))[0]
  if (arrival && (!notable || time(arrival.occurred_at) > time(notable.entry.created_at)))
    return {
      title: arrival.changes?.on_hand_delta
        ? t('到货已核实：在库 +{0}', [arrival.changes.on_hand_delta])
        : t('到货已核实'),
      at: arrival.occurred_at,
    }
  const latest = notable || items[0]
  return latest ? { title: latest.event.title, at: latest.entry.created_at } : null
}

/**
 * The Agent is not enabled and this mission has no Agent run or message to look back on. Entries
 * to the Agent then say so plainly; they still open the workspace.
 */
export const agentDormant = (
  session: { agentEnabled?: boolean } | null | undefined,
  agent: { run: unknown; messages: unknown[] },
) => !session?.agentEnabled && !agent.run && !agent.messages.length

/**
 * One-line watch summary for a work item: what the system waits for next, and the latest change.
 * Only business times are named (an expected arrival); when a check runs, when the item was
 * updated and when a change was recorded are real-world times and stay out of the line.
 */
export function watchSummary(item: Work, s: ShopState) {
  const mission = item.mission_id
    ? s.missions.find((m) => m.id === item.mission_id) || item.mission || null
    : null
  let timing = ''
  if (mission) {
    const arriving = s.inbounds
      .filter((i) => i.mission_id === mission.id && i.remaining_quantity > 0)
      .sort(
        (a, b) =>
          (Date.parse(a.expected_arrival_at || '') || Infinity) -
          (Date.parse(b.expected_arrival_at || '') || Infinity),
      )[0]
    if (arriving)
      timing = arriving.expected_arrival_at
        ? t('预计到货 {0} · {1} 件在途', [
            when(arriving.expected_arrival_at),
            arriving.remaining_quantity,
          ])
        : t('{0} 件在途，到货时间待供应商确认', [arriving.remaining_quantity])
    else if (mission.status === 'PAUSED') timing = t('主动跟进已暂停')
  }
  let change = ''
  if (mission && s.missionId === mission.id) {
    const latest = latestChange(mission.id, s)
    change = latest ? latest.title : t('暂无变化')
  } else if (!mission) {
    const p = workPresentation(item)
    change = p.detailIsOriginal ? p.detail : t(p.detail)
  }
  return { timing, change }
}

/**
 * The "next day" marker: the state version the page waits to move from, and until when (90 s).
 * The page's own advance starts it here; the presenter bar sets it for its own.
 */
export function useAdvanceMarker() {
  const { s } = useShop()
  const marker = useState('space-sync-advance', () => ({ from: null as number | null, until: 0 }))
  watch(
    () => s.busy,
    (busy) => {
      if (busy === '正在推进经营事件')
        marker.value = { from: s.dashboard?.state.state_version ?? null, until: Date.now() + 90000 }
    },
  )
  return marker
}

/** The owner's own writes to an order: each moves the facts, and a new plan follows in seconds. */
const OWNER_WRITES = ['正在登记到货', '正在登记供应商回复', '正在按对方数量成交', '正在撤回订单']

/**
 * "Next day" outdates the plan on purpose, and so does the owner recording a reply or an arrival:
 * for 90 s after the one and 30 s after the other, a plan whose facts changed, or a pending plan
 * whose facts are still syncing, is being re-checked as expected. The page keeps what it showed
 * under one quiet line (`rechecking`) instead of the "needs attention" card: a plan with a
 * purchase stays as a held card (`held`); a plan without one keeps the slot's quiet state, never
 * a "restock 0 units" card. `blocking` is the issue still worth that card; past the window it is
 * said again. `open`: the window itself, whatever the page has read so far.
 */
export function usePlanRecheck(issue: () => string | null) {
  const { s } = useShop()
  const advance = useAdvanceMarker()
  const written = useState('space-owner-write', () => 0)
  watch(
    () => s.busy,
    (busy) => {
      if (OWNER_WRITES.includes(busy)) written.value = Date.now() + 30000
    },
  )
  const open = ref(false)
  watch(
    () => Math.max(advance.value.until, written.value),
    (until, _, onCleanup) => {
      const left = until - Date.now()
      open.value = left > 0
      if (left <= 0) return
      const timer = setTimeout(() => (open.value = false), left)
      onCleanup(() => clearTimeout(timer))
    },
    { immediate: true },
  )
  // Syncing facts only hold a plan that still waits for the owner.
  const rechecking = computed(
    () =>
      open.value &&
      (issue() === 'changed' ||
        (issue() === 'stale' &&
          s.plan?.status === 'PENDING_APPROVAL' &&
          !!s.plan.proposed_purchase)),
  )
  const blocking = computed(() => (rechecking.value ? null : issue()))
  const held = computed(() => rechecking.value && !!s.plan?.proposed_purchase)
  return { open, rechecking, blocking, held }
}

/**
 * The work item's business line was read before the facts the page now shows (the owner's own
 * write refreshed the shop at once; the item follows a moment later). It then says what was true
 * before, such as "send the order" after the reply is in, and is left out until it catches up.
 */
export const behindFacts = (
  business: { state_version: number } | null | undefined,
  s: { dashboard: { state: { state_version: number } } | null },
) => !!business && !!s.dashboard && business.state_version < s.dashboard.state.state_version

export function useSpace() {
  const shop = useShop()
  const work = useWorkItems()
  const agent = useAgentConversation()
  const { s } = shop
  const item = computed(() => work.s.detail?.item || null)
  /** The item belongs to a restocking mission, whether or not its data has been read yet. */
  const linked = computed(() => !!item.value?.mission_id)
  /** The item's mission, once the shop has loaded it. */
  const mission = computed(() =>
    item.value?.mission_id && shop.mission.value?.id === item.value.mission_id
      ? shop.mission.value
      : null,
  )
  const ended = computed(() => ['COMPLETED', 'CANCELLED'].includes(mission.value?.status || ''))
  const actions = computed(() =>
    mission.value ? s.actions.filter((a) => a.mission_id === mission.value!.id) : [],
  )
  const openActions = computed(() =>
    actions.value.filter((a) => !settledActions.includes(a.status)),
  )
  /** Units already bought for this mission; a new plan keeps them and only fills the gap.
   * A partly filled order counts what the supplier accepted (its receipt), not what was asked. */
  const executed = computed(() =>
    actions.value
      .filter((a) => a.status === 'SUCCEEDED')
      .reduce(
        (n, a) => n + (a.receipt?.status === 'ACCEPTED' ? a.receipt.quantity : a.quantity),
        0,
      ),
  )
  const confirmationPending = computed(() => !!s.pending && s.pending.storeId === s.storeId)
  function badgeFor(issue: string | null): Badge {
    const current = item.value
    if (!current) return statusBadge({})
    if (!current.mission_id) return workBadge(current)
    const m = mission.value
    const business = behindFacts(current.business, s) ? null : current.business
    const badge = m
      ? statusBadge({
          work: workForBadge(current),
          mission: m.status,
          // A plan that proposes no purchase leaves nothing to confirm.
          plan: shop.plan.value?.proposed_purchase ? shop.plan.value.status : undefined,
          canDecide: shop.canDecide.value,
          actions: openActions.value.map((a) => a.status),
          inTransit: shop.stock.value?.in_transit,
          confirmationPending: confirmationPending.value,
          awaitingSupplier: shop.awaitingSupplier.value?.mission_id === m.id,
          // Every order whose goods the owner records, wherever the page records them.
          ownerRecordsArrival: shop.arrivalsToRecord.value.length > 0,
          business,
        })
      : confirmationPending.value
        ? statusBadge({ confirmationPending: true })
        : workBadge(current)
    // Whatever the "需要处理" card below says, the badge must not claim all is well. A new
    // store's first sync is not a problem, and the card says so in blue.
    const syncing = issue === 'stale' && firstSync(s.dashboard?.freshness)
    if (issue && !syncing && !ended.value && badge.tone !== 'amber')
      return { label: t('需要处理'), tone: 'amber' }
    return badge
  }
  /** Card briefly highlighted after an Agent tool finished reading or changing it (§4.4). */
  const target = useState('space-target', () => '')
  const isTarget = (name: string) => target.value === name || agent.runningTarget.value === name
  return {
    item,
    linked,
    mission,
    ended,
    actions,
    openActions,
    executed,
    confirmationPending,
    badgeFor,
    target,
    isTarget,
  }
}
