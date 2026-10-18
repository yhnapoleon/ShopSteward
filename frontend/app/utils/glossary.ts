import { t } from '~/i18n'
import { when } from '~/utils/presentation'

// Shop-owner vocabulary for statuses and identifiers (workspace redesign §6).
// Returned text is already localized for the current language.

export type BadgeTone = 'amber' | 'blue' | 'gray' | 'green'
export type Badge = { label: string; tone: BadgeTone }

export type BadgeInput = {
  /** Work item status (RECEIVED, PROCESSING, WAITING_INPUT, RESULT_READY, …). */
  work?: string | null
  /** Mission status (ACTIVE, PAUSED, COMPLETED, CANCELLED). */
  mission?: string | null
  /** Current plan status (PENDING_APPROVAL, …). */
  plan?: string | null
  /** The pending plan can be confirmed right now. */
  canDecide?: boolean
  /** Statuses of purchase orders that are not settled yet. */
  actions?: string[]
  /** Units in transit for the mission's product. */
  inTransit?: number | null
  /** A confirmation was sent but its result has not been read back. */
  confirmationPending?: boolean
  /** An order the owner sends by hand waits for the supplier's reply to be pasted back. */
  awaitingSupplier?: boolean
  /** Backend work-item summary, used only when nothing below matches. */
  business?: { code?: string | null; label?: string | null } | null
}

/** First matching rule wins; the order is the priority order of §6.2. */
export function statusBadge(input: BadgeInput): Badge {
  const actions = input.actions || []
  const code = input.business?.code || ''
  const badge = (label: string, tone: BadgeTone): Badge => ({ label: t(label), tone })
  if (input.confirmationPending || actions.includes('UNKNOWN') || code === 'UNKNOWN')
    return badge('需要处理', 'amber')
  if (input.plan === 'PENDING_APPROVAL' && input.canDecide) return badge('需要你拍板', 'amber')
  if (input.work === 'WAITING_INPUT') return badge('需要你补充', 'amber')
  // The system does not reach the supplier: the owner sends the order and pastes the reply.
  if (input.awaitingSupplier || code === 'AWAITING_SUPPLIER') return badge('待供应商确认', 'amber')
  if (
    actions.some((a) => ['QUEUED', 'EXECUTING'].includes(a)) ||
    ['QUEUED', 'EXECUTING'].includes(code)
  )
    return badge('正在核实采购', 'blue')
  if ((input.inTransit || 0) > 0 && input.plan !== 'PENDING_APPROVAL')
    return badge('等待到货', 'blue')
  if (input.work === 'PROCESSING') return badge('正在处理', 'blue')
  if (input.mission === 'PAUSED') return badge('已暂停', 'gray')
  if (['COMPLETED', 'CANCELLED'].includes(input.mission || '') || input.work === 'COMPLETED')
    return badge('已结束', 'gray')
  if (input.work === 'CANCELLED') return badge('已停止', 'gray')
  if (input.work === 'RESULT_READY' && !input.mission) return badge('结果已出', 'green')
  if (input.mission === 'ACTIVE') return badge('持续跟进中', 'green')
  return input.business?.label
    ? { label: t(input.business.label), tone: 'gray' }
    : badge('状态待核对', 'gray')
}

/**
 * A purchase order in the owner's words (§6.1): verification first, then its outcome, then how
 * much of it has arrived. Unlike the badge above, the label is the catalog key: callers translate
 * it with t() and may compare it, as the orders card does for "已到货".
 */
export function orderStatus(
  action: { status: string; channel?: string },
  inbound?: { arrival_status?: string | null } | null,
): Badge {
  // An order the owner sends by hand: the message is written, then it waits for the reply.
  if (action.channel === 'assisted' && action.status === 'QUEUED')
    return { label: '正在生成订单信息', tone: 'blue' }
  if (action.channel === 'assisted' && action.status === 'EXECUTING')
    return { label: '待供应商确认', tone: 'amber' }
  if (['QUEUED', 'EXECUTING'].includes(action.status))
    return { label: '正在核实采购', tone: 'blue' }
  if (action.status === 'UNKNOWN') return { label: '结果待核实', tone: 'amber' }
  if (action.status === 'FAILED') return { label: '采购未成功', tone: 'amber' }
  if (action.status === 'CANCELLED') return { label: '已取消', tone: 'gray' }
  if (action.status === 'STALE') return { label: '原方案失效', tone: 'gray' }
  if (inbound?.arrival_status === 'RECEIVED') return { label: '已到货', tone: 'green' }
  if (inbound?.arrival_status === 'PARTIALLY_RECEIVED') return { label: '部分到货', tone: 'blue' }
  return { label: '等待到货', tone: 'blue' }
}

/**
 * A new store whose business data has never been synced yet (§11). Its first sync takes a few
 * seconds; until then the data cannot be confirmed, but nothing is wrong.
 */
export const firstSync = (freshness?: { status: string; last_sync_at: string | null } | null) =>
  !!freshness && freshness.status !== 'FRESH' && !freshness.last_sync_at

const alertNames: Record<string, string> = {
  STOCKOUT_RISK: '缺货风险',
  CASH_CONSTRAINT: '现金约束',
  ACTION_EXCEPTION: '采购需核实',
  DATA_STALE: '数据未更新',
}
/** Reminder (alert) type in plain words; unknown types are shown as sent. */
export const alertName = (type: string) => (alertNames[type] ? t(alertNames[type]) : type)

/**
 * Store label (§6.3). Demo mode names the sample store by its creation time; the backend does
 * not expose that yet, so callers pass the best available time. Otherwise the id's tail is shown.
 */
export function storeDisplayName(
  store: { store_id: string; created_at?: string | null; simulation_time?: string | null },
  demo = false,
) {
  if (demo) return t('示例店铺 · {0}', [when(store.created_at || store.simulation_time)])
  return t('店铺尾号 {0}', [store.store_id.slice(-8)])
}

/** Supplier label (§6.3): the catalog name when there is one, else "供应商 001" from `supplier_001`. */
export function supplierDisplayName(id: string | null | undefined, name?: string | null) {
  if (name?.trim()) return name.trim()
  const number = /^supplier[_-]?(\d+)$/i.exec(id || '')?.[1]
  if (number) return t('供应商 {0}', [number.padStart(3, '0')])
  return id || t('未取得')
}
