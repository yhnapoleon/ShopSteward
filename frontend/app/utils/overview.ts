import type { Schema } from '~/types/models'

export type ReadContext = Schema<'ReadContext'>
export type CashPoint = { id: string; label: string; value: number; detail: string }
export type Collected<T> = { context: ReadContext; items: T[]; complete: boolean }

export function sameContext(a: ReadContext, b: ReadContext) {
  return (
    a.store_id === b.store_id &&
    a.state_version === b.state_version &&
    a.source_sequence === b.source_sequence &&
    a.simulation_time === b.simulation_time
  )
}
export function matchesState(context: ReadContext, dashboard: Schema<'Dashboard'>) {
  return (
    context.store_id === dashboard.state.store_id &&
    context.state_version === dashboard.state.state_version &&
    context.simulation_time === dashboard.state.simulation_time
  )
}
export function utcDay(value: string) {
  return value.slice(0, 10)
}
export function utcTime(value: string | null | undefined) {
  if (!value) return '时点未知'
  const d = new Date(value)
  if (!Number.isFinite(d.getTime())) return '时点未知'
  return (
    new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'UTC',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(d) + ' UTC'
  )
}
// Calendar dates are explicit UTC days. The exclusive end includes the chosen last day.
export function salesRange(clock: string | null | undefined, days: number, start = '', end = '') {
  if (!clock) return null
  const anchor = new Date(clock)
  if (!Number.isFinite(anchor.getTime())) return null
  const last = Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), anchor.getUTCDate())
  const from = start ? Date.parse(start + 'T00:00:00Z') : last - (days - 1) * 86400000
  const toDay = end ? Date.parse(end + 'T00:00:00Z') : last
  if (
    !Number.isFinite(from) ||
    !Number.isFinite(toDay) ||
    from > toDay ||
    toDay > last ||
    toDay - from >= 90 * 86400000
  )
    return null
  return { from: new Date(from).toISOString(), to: new Date(toDay + 86400000).toISOString() }
}
export function cashHistory(
  ledger: Collected<Schema<'LedgerEntryView'>> | null,
  dashboard: Schema<'Dashboard'> | null,
): CashPoint[] {
  if (!ledger?.complete || !dashboard || !matchesState(ledger.context, dashboard)) return []
  const entries = [...ledger.items].sort((a, b) => a.state_version - b.state_version)
  if (entries.filter((e) => e.effect_type === 'INIT').length !== 1 || !entries[0]?.opening_state)
    return []
  if (new Set(entries.map((e) => e.id)).size !== entries.length) return []
  let balance = entries[0].opening_state.cash_minor
  if (!Number.isSafeInteger(balance)) return []
  const points: CashPoint[] = [
    { id: entries[0].id, label: '初始', value: balance, detail: '初始现金余额' },
  ]
  for (const e of entries.slice(1)) {
    if (!e.changes) return []
    const delta = e.changes.cash_delta_minor
    balance += delta
    if (!Number.isSafeInteger(balance)) return []
    if (delta !== 0)
      points.push({
        id: e.id,
        label: `采购 ${points.length}`,
        value: balance,
        detail: '采购已受理',
      })
  }
  return balance === dashboard.state.cash_minor ? points : []
}
