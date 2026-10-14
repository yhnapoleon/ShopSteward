import { t } from '~/i18n'
import type { Schema } from '~/types/models'
import { money, when } from '~/utils/presentation'
import { alertName } from '~/utils/glossary'

// Mission timeline entries in the shop owner's words. The backend summary is parsed only for
// the fixed sentence shapes it writes today; anything unrecognised is shown as written.
// Returned text is already localized for the current language and can be displayed directly.

type Entry = Schema<'TimelineEntry'>
export type TimelineTone = 'green' | 'amber' | 'gray' | 'blue'
export type TimelineEvent = {
  title: string
  detail?: string
  tone: TimelineTone
  /** A person icon for the owner's own actions, a dot for system events. */
  icon: 'user' | 'dot'
  /** Routine events need no attention and collapse into one line. */
  routine: boolean
  references: Schema<'Reference'>[]
}
export type TimelineRow =
  | { kind: 'event'; key: string; entry: Entry; event: TimelineEvent }
  | {
      kind: 'group'
      key: string
      label: string
      tone: TimelineTone
      earliest: string
      latest: string
      items: { entry: Entry; event: TimelineEvent }[]
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
const checkResults: Record<string, string> = {
  'Candidate comparison saved': '检查完成：已生成新方案',
  'Existing valid plan reused': '检查完成：方案无变化',
  'Mission inactive or an action is pending': '检查完成：有采购待核实，本次跳过',
  DATA_STALE: '检查完成：数据未更新，未能检查',
  // Other fixed outcomes the planning job writes today.
  OFFER_EXPIRED: '检查完成：供货报价已过期，未能检查',
  PLAN_INPUT_EXPIRED: '检查完成：方案依据已过期，未能检查',
  'Inputs changed; a follow-up check was requested': '检查完成：经营情况有变化，已安排复查',
  'Previously rejected intent suppressed': '检查完成：沿用你上次不采购的决定',
}
const checkTones: Record<string, TimelineTone> = {
  HEALTHY: 'green',
  ANOMALY: 'amber',
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
  }
}

export function describeEvent(entry: Entry): TimelineEvent {
  const summary = entry.summary.trim()
  const base = {
    title: summary,
    tone: 'gray' as TimelineTone,
    icon: entry.actor_type === 'USER' ? ('user' as const) : ('dot' as const),
    routine: false,
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
      return plan ? { ...base, ...plan } : base
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
      if (!m) return base
      const [, status, result] = m as unknown as [string, string, string]
      const known = checkResults[result.trim()]
      return {
        ...base,
        title: known ? t(known) : t('检查完成：{0}', [result.trim()]),
        tone: checkTones[status] || 'gray',
        detail: status === 'ANOMALY' ? t('这是风险判断，非系统故障') : undefined,
        routine: result.trim() === 'Existing valid plan reused',
      }
    }
    case 'ALERT_OPENED':
    case 'ALERT_ESCALATED': {
      const m = /^([A-Z_]+)：([\s\S]*)$/.exec(summary)
      if (!m) return base
      return {
        ...base,
        title: t('发现{0}：{1}', [alertName(m[1]!), t(m[2]!.trim())]),
        tone: 'amber',
      }
    }
    case 'ALERT_RESOLVED': {
      const type = /^([A-Z_]+)：/.exec(summary)?.[1]
      if (!type) return base
      return { ...base, title: t('{0}已解除', [alertName(type)]), tone: 'green', routine: true }
    }
    case 'ALERT_ACKNOWLEDGED': {
      const type = /^已知晓([A-Z_]+)；/.exec(summary)?.[1]
      if (!type) return base
      return { ...base, title: t('你已知晓{0}', [alertName(type)]), detail: t('风险尚未解除') }
    }
    case 'ACTION_EXECUTING':
      return { ...base, title: t('采购单已发出，资金已预留'), tone: 'blue' }
    case 'ACTION_SUCCEEDED':
      return { ...base, title: t('供应商已受理采购'), tone: 'green' }
    default: {
      const result = actionResults[entry.type]
      if (!result) return base
      const status = entry.type.slice('ACTION_'.length)
      const reason = summary && summary !== status ? summary : ''
      return {
        ...base,
        title: t(result.title),
        tone: result.tone,
        detail: reason ? (actionReasons[reason] ? t(actionReasons[reason]) : reason) : undefined,
      }
    }
  }
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
  const rows: TimelineRow[] = []
  let run: { entry: Entry; event: TimelineEvent }[] = []
  let mode: 'routine' | 'repeat' | null = null
  const flush = () => {
    if (run.length === 1) {
      const only = run[0]!
      rows.push({ kind: 'event', key: only.entry.id, entry: only.entry, event: only.event })
    } else if (run.length > 1) {
      const { earliest, latest } = span(run)
      const label =
        mode === 'repeat'
          ? t('{0} · 连续 {1} 次 · 最近 {2}', [run[0]!.event.title, run.length, when(latest)])
          : run.every((i) => i.entry.type === 'CHECK_COMPLETED')
            ? t('{0} 次例行检查，方案无变化 · 最近 {1}', [run.length, when(latest)])
            : t('{0} 条例行记录，无需处理 · 最近 {1}', [run.length, when(latest)])
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
  for (const entry of entries) {
    const event = describeEvent(entry)
    const item = { entry, event }
    if (event.routine) {
      if (mode !== 'routine') flush()
      mode = 'routine'
      run.push(item)
    } else if (event.icon === 'user') {
      flush()
      rows.push({ kind: 'event', key: entry.id, entry, event })
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

/** One line per row, for the plain-text business brief. */
export function timelineLines(entries: Entry[]) {
  return groupTimeline(entries).map((row) =>
    row.kind === 'group'
      ? `${when(row.earliest)} ${row.label}`
      : [`${when(row.entry.created_at)} ${row.event.title}`, row.event.detail]
          .filter(Boolean)
          .join(' · '),
  )
}
