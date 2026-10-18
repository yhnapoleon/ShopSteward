import { t } from '~/i18n'
import type { Schema } from '~/types/models'
import { money, when } from '~/utils/presentation'
import { alertName } from '~/utils/glossary'

// Mission timeline entries in the shop owner's words. The backend summary is parsed only for
// the fixed sentence shapes it writes today; anything unrecognised is shown as written.
// Returned text is already localized for the current language and can be displayed directly.

type Entry = Schema<'TimelineEntry'>
export type TimelineTone = 'green' | 'amber' | 'gray' | 'blue'
/** What a row is about. It names folded rows and picks a mission's latest change. */
export type TimelineKind = 'plan' | 'check' | 'order' | 'alert' | 'other'
export type TimelineEvent = {
  title: string
  detail?: string
  tone: TimelineTone
  /** A person icon for the owner's own actions, a dot for system events. */
  icon: 'user' | 'dot'
  /** Routine events need no attention and collapse into one line. */
  routine: boolean
  kind: TimelineKind
  /** Plans only: the plan proposes no purchase and leaves no shortage. */
  quiet?: boolean
  references: Schema<'Reference'>[]
}
/** One row before folding. A check that saved a plan carries that plan's entry as well. */
export type TimelineItem = { entry: Entry; event: TimelineEvent; plan?: Entry }
export type TimelineRow =
  | { kind: 'event'; key: string; entry: Entry; event: TimelineEvent }
  | {
      kind: 'group'
      key: string
      label: string
      tone: TimelineTone
      earliest: string
      latest: string
      items: TimelineItem[]
    }

const missionControls: Record<string, string> = {
  pause: '已暂停主动跟进',
  resume: '恢复主动跟进',
  complete: '结束委托',
  cancel: '取消委托',
}
const proposal = /^推荐采购(\d+)件；预计支出(-?\d+)分，采购后可用现金(-?\d+)分，剩余缺口(\d+)件。$/
const noProposal = '当前候选均不满足采购约束，未提出采购。'
const checkLine = /^检查([A-Z_]+)：([\s\S]*)（任务[^（）]*）$/
const savedComparison = 'Candidate comparison saved'
const emergencyHolds = 'An emergency case holds this item until it ends'
const checkResults: Record<string, string> = {
  [savedComparison]: '检查完成：已生成新方案',
  'Existing valid plan reused': '检查完成：方案无变化',
  'Mission inactive or an action is pending': '检查完成：有采购待核实，本次跳过',
  DATA_STALE: '检查完成：数据未更新，未能检查',
  // Other fixed outcomes the planning job writes today.
  OFFER_EXPIRED: '检查完成：供货报价已过期，未能检查',
  PLAN_INPUT_EXPIRED: '检查完成：方案依据已过期，未能检查',
  'Inputs changed; a follow-up check was requested': '检查完成：经营情况有变化，已安排复查',
  'Previously rejected intent suppressed': '检查完成：沿用你上次不采购的决定',
  // While an emergency case holds the item (backend/app/planning/jobs.py); the last one only
  // appears in timelines written before cases held the item.
  'Recovery plan awaits explicit approval': '检查完成：应急方案等你确认，本次跳过',
  [emergencyHolds]: '检查完成：应急事项处理中，例行补货暂停',
  'Recovery purchase is unresolved': '检查完成：应急采购还没有结果，本次跳过',
  // Why a check could not run (backend/app/planning/snapshot.py prepared.reason).
  MISSION_INACTIVE_OR_ACTION_PENDING: '检查完成：有采购待核实，本次跳过',
  MISSION_NOT_FOUND: '检查完成：找不到这项委托，未能检查',
  FORECAST_UNAVAILABLE: '检查完成：需求预测暂不可用，未能检查',
  INPUT_UNAVAILABLE: '检查完成：预测或报价数据缺失，未能检查',
  INBOUND_STATE_MISMATCH: '检查完成：在途记录对不上，未能检查',
  INVALID_FORECAST_OR_OFFER: '检查完成：预测或报价数据无法识别，未能检查',
}
// Entries an emergency case writes; their sentences are translated as whole templates.
const caseEntries: Record<string, { tone: TimelineTone; kind: TimelineKind }> = {
  CASE_DECISION: { tone: 'gray', kind: 'other' },
  CASE_RECHECK_REQUIRED: { tone: 'amber', kind: 'other' },
  CASE_RESOLVED: { tone: 'green', kind: 'order' },
  SUPPLIER_REPLY_PARTIAL: { tone: 'amber', kind: 'order' },
  PURCHASE_PARTIALLY_ACCEPTED: { tone: 'blue', kind: 'order' },
}
// A risk a check finds is reported by its own "发现…" reminder row, which alone is amber.
const checkTones: Record<string, TimelineTone> = {
  HEALTHY: 'green',
  ANOMALY: 'gray',
  INCONCLUSIVE: 'gray',
  SKIPPED: 'gray',
}
const actionResults: Record<string, { title: string; tone: TimelineTone }> = {
  ACTION_UNKNOWN: { title: '采购结果待核实', tone: 'amber' },
  ACTION_FAILED: { title: '采购未成功', tone: 'amber' },
  ACTION_CANCELLED: { title: '采购已取消', tone: 'gray' },
  ACTION_STALE: { title: '原方案失效', tone: 'gray' },
}
const actionReasons: Record<string, string> = {
  SUPPLIER_REJECTED: '供应商拒绝了这笔采购',
  SUPPLIER_PENDING: '供应商尚未给出结果',
  RECEIPT_CONFLICT: '回执与原采购不一致',
  INVALID_SOURCE_RESPONSE: '供应商回执无法识别',
}

function planTitle(summary: string, revised: boolean) {
  if (summary === noProposal)
    return {
      title: t(revised ? '方案已修订：没有可行的采购' : '新方案：没有可行的采购'),
      tone: 'amber' as const,
      quiet: false,
    }
  const m = proposal.exec(summary)
  if (!m) return null
  const [quantity, spend, cash, shortage] = m.slice(1).map(Number) as [
    number,
    number,
    number,
    number,
  ]
  return {
    title:
      quantity > 0
        ? t(
            revised
              ? '方案已修订：建议补 {0} 件 · 支出 {1} · 采购后现金 {2} · 缺口 {3} 件'
              : '新方案：建议补 {0} 件 · 支出 {1} · 采购后现金 {2} · 缺口 {3} 件',
            [quantity, money(spend), money(cash), shortage],
          )
        : t(
            revised
              ? '方案已修订：建议本轮不补货 · 缺口 {0} 件'
              : '新方案：建议本轮不补货 · 缺口 {0} 件',
            [shortage],
          ),
    tone: 'blue' as const,
    // Nothing to buy and nothing missing: a routine result, folded with the checks.
    quiet: quantity === 0 && shortage === 0,
  }
}

export function describeEvent(entry: Entry): TimelineEvent {
  const summary = entry.summary.trim()
  const owner = entry.actor_type === 'USER'
  const base = {
    title: summary,
    tone: 'gray' as TimelineTone,
    icon: owner ? ('user' as const) : ('dot' as const),
    routine: false,
    kind: 'other' as TimelineKind,
    references: entry.references,
  }
  switch (entry.type) {
    case 'MISSION_CREATED':
      return { ...base, title: t('建立备货委托'), tone: 'blue' }
    case 'MISSION_CONTROLLED': {
      const title = missionControls[summary]
      return title
        ? { ...base, title: t(title), tone: summary === 'resume' ? 'blue' : 'gray' }
        : base
    }
    case 'PLAN_CREATED':
    case 'PLAN_REVISED': {
      const plan = planTitle(summary, entry.type === 'PLAN_REVISED')
      // The owner's own revision always keeps a row of its own.
      return plan
        ? { ...base, ...plan, kind: 'plan', routine: plan.quiet && !owner }
        : { ...base, kind: 'plan' }
    }
    case 'PLAN_DECIDED':
      if (summary === 'approve') return { ...base, title: t('你确认了采购'), tone: 'blue' }
      if (summary === 'reject') return { ...base, title: t('你选择本轮不采购') }
      return base
    case 'CHECK_REQUESTED': {
      const reason = /^([\s\S]*)（任务[^（）]*）$/.exec(summary)?.[1]?.trim()
      return {
        ...base,
        title: t('你要求重新检查'),
        // The reason is the requester's own words; the default placeholder adds nothing.
        detail: reason && reason !== 'Manual check' ? reason : undefined,
      }
    }
    case 'CHECK_COMPLETED': {
      const m = checkLine.exec(summary)
      if (!m) return { ...base, kind: 'check' }
      const [, status, result] = m as unknown as [string, string, string]
      const known = checkResults[result.trim()]
      return {
        ...base,
        title: known ? t(known) : t('检查完成：{0}', [result.trim()]),
        tone: checkTones[status] || 'gray',
        kind: 'check',
        routine: ['Existing valid plan reused', emergencyHolds].includes(result.trim()),
      }
    }
    case 'ALERT_OPENED':
    case 'ALERT_ESCALATED': {
      const m = /^([A-Z_]+)：([\s\S]*)$/.exec(summary)
      if (!m) return { ...base, kind: 'alert' }
      return {
        ...base,
        title: t('发现{0}：{1}', [alertName(m[1]!), t(m[2]!.trim())]),
        tone: 'amber',
        kind: 'alert',
      }
    }
    case 'ALERT_RESOLVED': {
      const type = /^([A-Z_]+)：/.exec(summary)?.[1]
      if (!type) return base
      return {
        ...base,
        title: t('{0}已解除', [alertName(type)]),
        tone: 'green',
        kind: 'alert',
        routine: true,
      }
    }
    case 'ALERT_ACKNOWLEDGED': {
      const type = /^已知晓([A-Z_]+)；/.exec(summary)?.[1]
      if (!type) return base
      return { ...base, title: t('你已知晓{0}', [alertName(type)]), detail: t('风险尚未解除') }
    }
    case 'ACTION_EXECUTING':
      return { ...base, title: t('采购单已发出，资金已预留'), tone: 'blue', kind: 'order' }
    case 'ACTION_SUCCEEDED':
      return { ...base, title: t('供应商已受理采购'), tone: 'green', kind: 'order' }
    default: {
      const written = caseEntries[entry.type]
      if (written) return { ...base, ...written, title: t(summary) }
      const result = actionResults[entry.type]
      if (!result) return base
      const status = entry.type.slice('ACTION_'.length)
      const reason = summary && summary !== status ? summary : ''
      return {
        ...base,
        title: t(result.title),
        tone: result.tone,
        kind: 'order',
        detail: reason ? (actionReasons[reason] ? t(actionReasons[reason]) : reason) : undefined,
      }
    }
  }
}

const isPlan = (entry: Entry) => entry.type === 'PLAN_CREATED' || entry.type === 'PLAN_REVISED'
const planId = (entry: Entry) => entry.references.find((r) => r.type === 'plan')?.id
const savesPlan = (entry: Entry) =>
  entry.type === 'CHECK_COMPLETED' &&
  checkLine.exec(entry.summary.trim())?.[2]?.trim() === savedComparison

/**
 * The plan a "comparison saved" check wrote. The check records its plan first, then any reminder
 * it opened or resolved, then its own line, all within moments: so the plan is one of the next
 * few, older entries, matched by the plan both reference (or, without references, the next plan
 * entry with only reminders in between).
 */
function planOf(entries: Entry[], index: number, taken: Set<number>) {
  const check = entries[index]!
  const id = planId(check)
  const at = Date.parse(check.created_at)
  for (let i = index + 1; i < entries.length && i <= index + 4; i++) {
    const entry = entries[i]!
    if (Math.abs(Date.parse(entry.created_at) - at) > 5000) break
    if (isPlan(entry) && !taken.has(i) && (!id || !planId(entry) || planId(entry) === id)) return i
    if (!id && !entry.type.startsWith('ALERT_')) break
  }
  return -1
}

/**
 * The timeline in the owner's words, newest first and not yet folded. A check that saved a new
 * plan and that plan become one row: the plan's words, "由检查生成" below.
 */
export function timelineItems(entries: Entry[]): TimelineItem[] {
  const pairs = new Map<number, number>()
  const taken = new Set<number>()
  entries.forEach((entry, index) => {
    if (!savesPlan(entry)) return
    const plan = planOf(entries, index, taken)
    if (plan < 0) return
    pairs.set(index, plan)
    taken.add(plan)
  })
  const items: TimelineItem[] = []
  entries.forEach((entry, index) => {
    if (taken.has(index)) return
    const paired = pairs.get(index)
    if (paired === undefined) {
      items.push({ entry, event: describeEvent(entry) })
      return
    }
    const plan = entries[paired]!
    const references = new Map(
      [...plan.references, ...entry.references].map((r) => [`${r.type}:${r.id}`, r]),
    )
    items.push({
      entry,
      plan,
      event: {
        ...describeEvent(plan),
        detail: t('由检查生成'),
        references: [...references.values()],
      },
    })
  })
  return items
}

const span = (items: { entry: Entry }[]) => {
  const times = items.map((i) => Date.parse(i.entry.created_at)).filter((n) => !Number.isNaN(n))
  const iso = (n: number) => new Date(n).toISOString()
  return times.length
    ? { earliest: iso(Math.min(...times)), latest: iso(Math.max(...times)) }
    : { earliest: items.at(-1)!.entry.created_at, latest: items[0]!.entry.created_at }
}

/**
 * Collapses consecutive routine events into one expandable row. Repeated identical system
 * results (for example a long run of "data not updated" checks) collapse the same way; the
 * owner's own actions are never grouped.
 */
export function groupTimeline(entries: Entry[]): TimelineRow[] {
  const items = timelineItems(entries)
  // An unchanged-plan check kept a plan: the one it references, else the nearest older plan row.
  // "settled" marks the checks whose kept plan is known to propose no purchase; a plan whose
  // entry is not loaded is not known.
  const quietPlans = new Map<string, boolean>()
  for (const item of items) {
    const id = item.event.kind === 'plan' ? planId(item.plan || item.entry) : undefined
    if (id) quietPlans.set(id, !!item.event.quiet)
  }
  const settled = new Set<TimelineItem>()
  let quiet = false
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i]!
    if (item.event.kind === 'plan') quiet = !!item.event.quiet
    else if (item.event.kind === 'check') {
      const kept = planId(item.entry)
      if (kept ? quietPlans.get(kept) : quiet) settled.add(item)
    }
  }
  const rows: TimelineRow[] = []
  let run: TimelineItem[] = []
  let mode: 'routine' | 'repeat' | null = null
  // Checks and plans without a purchase read "无需采购" only when that holds at the run's newest
  // row; while a purchase plan stays in force the checks merely left it unchanged.
  const routineLabel = (latest: string) => {
    const head = run[0]!
    const checks = run.every((i) => i.event.kind === 'check' || i.event.kind === 'plan')
    if (checks && (head.event.kind === 'plan' || settled.has(head)))
      return t('{0} 次检查，无需采购 · 最近 {1}', [run.length, when(latest)])
    if (run.every((i) => i.event.kind === 'check'))
      return t('{0} 次例行检查，方案无变化 · 最近 {1}', [run.length, when(latest)])
    return t('{0} 条例行记录，无需处理 · 最近 {1}', [run.length, when(latest)])
  }
  const flush = () => {
    if (run.length === 1) {
      const only = run[0]!
      rows.push({ kind: 'event', key: only.entry.id, entry: only.entry, event: only.event })
    } else if (run.length > 1) {
      const { earliest, latest } = span(run)
      const label =
        mode === 'repeat'
          ? t('{0} · 连续 {1} 次 · 最近 {2}', [run[0]!.event.title, run.length, when(latest)])
          : routineLabel(latest)
      rows.push({
        kind: 'group',
        key: 'group:' + run[0]!.entry.id,
        label,
        tone: run.some((i) => i.event.tone === 'amber') ? 'amber' : run[0]!.event.tone,
        earliest,
        latest,
        items: run,
      })
    }
    run = []
    mode = null
  }
  for (const item of items) {
    const { entry, event } = item
    if (event.icon === 'user') {
      flush()
      rows.push({ kind: 'event', key: entry.id, entry, event })
    } else if (event.routine) {
      if (mode !== 'routine') flush()
      mode = 'routine'
      run.push(item)
    } else if (mode === 'repeat' && run[0]!.event.title === event.title) {
      run.push(item)
    } else {
      flush()
      mode = 'repeat'
      run.push(item)
    }
  }
  flush()
  return rows
}

/** One line per row (newest first, at most `limit`), for the plain-text business brief. */
export function timelineLines(entries: Entry[], limit = Infinity) {
  return groupTimeline(entries)
    .slice(0, limit)
    .map((row) =>
      row.kind === 'group'
        ? `${when(row.earliest)} ${row.label}`
        : [`${when(row.entry.created_at)} ${row.event.title}`, row.event.detail]
            .filter(Boolean)
            .join(' · '),
    )
}
