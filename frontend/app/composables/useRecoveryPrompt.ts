import { t } from '~/i18n'
import { api, query } from '~/utils/api'
import { supplierDisplayName } from '~/utils/glossary'
import type { RecoveryCase } from '~/types/recovery'
import {
  demandFrom,
  flowState,
  named,
  projectWithout,
  recoveryTrigger,
  settlements,
  type RecoveryReason,
} from '~/utils/recovery'

// Whether the current mission needs an emergency restock its regular plan cannot give (§18), and
// the one line the today page says about it. The store's recovery Cases are read once per store
// so a restock already under way is not offered again.

export function useRecoveryPrompt() {
  const shop = useShop()
  const { s, mission } = shop
  const work = useWorkItems()
  const launcher = useRecoveryLaunch()
  const cache = useState('recovery-cases', () => ({ storeId: '', items: [] as RecoveryCase[] }))
  async function load() {
    const store = s.storeId
    if (!store || !s.session?.recoveryCases) return
    try {
      const page = await api<{ items: RecoveryCase[] }>(
        '/api/v1/operations-cases' + query({ store_id: store }),
      )
      if (store === s.storeId) cache.value = { storeId: store, items: page.items }
    } catch {
      if (store === s.storeId) cache.value = { storeId: store, items: [] }
    }
  }
  const trigger = computed(() =>
    mission.value?.status === 'ACTIVE'
      ? recoveryTrigger({
          missionId: mission.value.id,
          plan: shop.plan.value,
          actions: s.actions,
          inbounds: s.inbounds,
          alerts: s.alerts,
        })
      : null,
  )
  /** A restock of this mission that has not ended (by the same reading the work page uses). */
  const underWay = computed(() => {
    const m = mission.value
    if (!m || cache.value.storeId !== s.storeId) return false
    const latest = cache.value.items.find(
      (c) => c.mission_id === m.id && !['CLOSED', 'CANCELLED'].includes(c.status),
    )
    if (!latest) return false
    const action = (latest.action_id && s.actions.find((a) => a.id === latest.action_id)) || null
    const ids = new Set(latest.evidence.filter((e) => e.kind === 'inbound_order').map((e) => e.id))
    return !flowState({
      detail: latest,
      action,
      inbound: (action && s.inbounds.find((i) => i.action_id === action.id)) || null,
      originals: s.inbounds.filter((i) => ids.has(i.action_id)),
    }).ended
  })
  const allowed = computed(
    () =>
      !!s.session?.recoveryCases &&
      shop.hasRole('operator') &&
      work.s.available &&
      cache.value.storeId === s.storeId,
  )
  const shown = computed(() => allowed.value && !!trigger.value && !underWay.value)
  /** The projected seven-day gap without a new purchase, on the mission's demand assumption. */
  const gap = computed(() => {
    const clock = s.dashboard?.state.simulation_time
    const stock = shop.stock.value
    if (!clock || !stock || !mission.value) return null
    const plan = demandFrom({ plan: shop.plan.value, remainingDemand: stock.remaining_demand })
    return projectWithout(
      stock.on_hand,
      plan.values,
      settlements(clock),
      s.inbounds
        .filter((i) => i.sku_id === mission.value!.sku_id && i.remaining_quantity > 0)
        .map((i) => ({ quantity: i.remaining_quantity, at: i.expected_arrival_at })),
      clock,
    ).lost
  })
  const tags: Record<RecoveryReason, string> = {
    manual: '应急补货',
    late: '原订单晚到',
    stockout: '缺货风险',
    cash: '资金缺口',
    infeasible: '没有可行采购',
    failed: '采购未成功',
    declined: '供应商拒单',
    partial: '只能供应一部分',
    expired: '报价已过期',
  }
  const tag = computed(() => (trigger.value ? t(tags[trigger.value.reason]) : ''))
  const title = computed(() => {
    const value = trigger.value
    if (!value) return ''
    const name = supplierDisplayName(value.supplier)
    const lead: Record<RecoveryReason, string> = {
      manual: '可以找别家应急补货',
      late: '原订单晚到',
      stockout: '按常规方案补完仍会缺货',
      cash: '现金不够按原计划补货',
      infeasible: '常规方案买不了',
      failed: '这笔采购没有成功',
      declined: '{0}拒单了',
      partial: '{0}只能供应一部分',
      expired: '报价已过期',
    }
    const head = named(lead[value.reason], [name])
    // A plan that still leaves a gap names that gap; otherwise the gap without any purchase.
    const short = value.gap ?? gap.value
    return short ? t('{0}：7 天预计缺 {1} 件', [head, short]) : head
  })
  function launch() {
    const value = trigger.value
    if (!value || !mission.value) return null
    launcher.request({
      missionId: mission.value.id,
      reason: value.reason,
      exclude: value.reason === 'declined' ? value.supplier || null : null,
      gap: value.gap ?? gap.value,
    })
    return mission.value.id
  }
  return { load, trigger, shown, tag, title, launch, underWay }
}
