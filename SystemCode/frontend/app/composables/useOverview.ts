import type { Schema } from '~/types/models'
import { api, query } from '~/utils/api'
import {
  matchesState,
  sameContext,
  salesRange,
  type Collected,
  type ReadContext,
} from '~/utils/overview'

// A view-local reader: no commands, no business state writes, no shared Agent/approval state.
export function useOverview() {
  const { s } = useShop()
  const dashboard = shallowRef<Schema<'Dashboard'> | null>(null)
  const summary = shallowRef<Schema<'SaleSummary'> | null>(null)
  const inbounds = shallowRef<Collected<Schema<'InboundItem'>> | null>(null)
  const ledger = shallowRef<Collected<Schema<'LedgerEntryView'>> | null>(null)
  const error = reactive({ facts: '', sales: '', inbounds: '', ledger: '' })
  const refreshing = ref(false)
  const days = ref(7)
  const custom = reactive({ start: '', end: '' })
  const revision = ref(0)
  let generation = 0,
    disposed = false
  let timer: ReturnType<typeof setInterval> | undefined

  async function collect<T>(
    path: string,
    store: string,
    current: () => boolean,
  ): Promise<Collected<T>> {
    let cursor: string | null = null,
      context: ReadContext | null = null
    const items: T[] = [],
      seen = new Set<string>()
    // Bounded reads. A cap is never silently presented as a total or full history.
    for (let page = 0; page < 20; page++) {
      if (!current()) throw Error('读取已取消')
      const result: { context: ReadContext; items: T[]; next_cursor: string | null } = await api<{
        context: ReadContext
        items: T[]
        next_cursor: string | null
      }>(path + query({ store_id: store, limit: 100, cursor }))
      if (result.context.store_id !== store || (context && !sameContext(context, result.context)))
        throw Error('读取期间经营数据发生变化，请刷新。')
      context ??= result.context
      if (result.context.freshness.status !== 'FRESH') context = result.context
      items.push(...result.items)
      cursor = result.next_cursor
      if (!cursor) return { items, context: context!, complete: true }
      if (seen.has(cursor)) throw Error('分页未能继续，请刷新。')
      seen.add(cursor)
    }
    return { items, context: context!, complete: false }
  }
  async function refresh() {
    const id = s.storeId,
      g = ++generation
    const current = () => !disposed && generation === g && s.storeId === id
    if (!id) {
      refreshing.value = false
      return
    }
    refreshing.value = true
    try {
      const facts = await api<Schema<'Dashboard'>>('/api/v1/dashboard' + query({ store_id: id }))
      if (!current()) return
      if (facts.state.store_id !== id) throw Error('经营环境不匹配，请刷新。')
      dashboard.value = facts
      error.facts = ''
      const range = salesRange(facts.state.simulation_time, days.value, custom.start, custom.end)
      const results = await Promise.allSettled([
        range
          ? api<Schema<'SaleSummary'>>('/api/v1/sales/summary' + query({ store_id: id, ...range }))
          : Promise.reject(Error('经营时点未知，暂不能查询销售区间。')),
        collect<Schema<'InboundItem'>>('/api/v1/inbounds', id, current),
        collect<Schema<'LedgerEntryView'>>('/api/v1/ledger-entries', id, current),
      ])
      if (!current()) return
      const [saleResult, inboundResult, ledgerResult] = results
      if (saleResult.status === 'fulfilled' && saleResult.value.context.store_id === id) {
        summary.value = saleResult.value
        error.sales = ''
      } else
        error.sales =
          saleResult.status === 'rejected'
            ? String(saleResult.reason.message || '销售读取失败')
            : '销售所属环境不一致。'
      if (inboundResult.status === 'fulfilled') {
        inbounds.value = inboundResult.value
        error.inbounds = ''
      } else error.inbounds = String(inboundResult.reason.message || '到货读取失败')
      if (ledgerResult.status === 'fulfilled') {
        ledger.value = ledgerResult.value
        error.ledger = ''
      } else error.ledger = String(ledgerResult.reason.message || '流水读取失败')
      revision.value++
    } catch (e) {
      if (current()) error.facts = (e as Error).message
    } finally {
      if (current()) refreshing.value = false
    }
  }
  function setRange(count: number, start = '', end = '') {
    if (!salesRange(dashboard.value?.state.simulation_time, count, start, end)) return false
    days.value = count
    custom.start = start
    custom.end = end
    summary.value = null
    error.sales = ''
    void refresh()
    return true
  }
  const mixed = computed(() =>
    Boolean(
      dashboard.value &&
        [summary.value, inbounds.value, ledger.value].some(
          (value) => value && !matchesState(value.context, dashboard.value!),
        ),
    ),
  )
  watch(
    () => [s.storeId, s.storeVersion] as const,
    () => {
      generation++
      dashboard.value = null
      summary.value = null
      inbounds.value = null
      ledger.value = null
      Object.assign(error, { facts: '', sales: '', inbounds: '', ledger: '' })
      custom.start = ''
      custom.end = ''
      days.value = 7
      void refresh()
    },
    { immediate: true },
  )
  // A state change refreshes the read view without changing the existing polling protocol.
  watch(
    () => s.dashboard?.state.state_version,
    (value) => {
      if (
        value &&
        dashboard.value &&
        value !== dashboard.value.state.state_version &&
        !refreshing.value
      )
        void refresh()
    },
  )
  onMounted(() => {
    timer = setInterval(() => {
      if (!document.hidden && !refreshing.value) void refresh()
    }, 12000)
  })
  onUnmounted(() => {
    disposed = true
    generation++
    if (timer) clearInterval(timer)
  })
  return {
    dashboard,
    summary,
    inbounds,
    ledger,
    error,
    refreshing,
    mixed,
    days,
    custom,
    revision,
    refresh,
    setRange,
  }
}
