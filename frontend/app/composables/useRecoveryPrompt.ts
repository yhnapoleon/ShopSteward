import { t } from '~/i18n'
import { api, query } from '~/utils/api'
import { rememberSupplierNames, supplierDisplayName } from '~/utils/glossary'
import type { RecoveryCase, Sourcing } from '~/types/recovery'
import type { ForecastCurrent } from '~/types/forecast'
import {
  TERMINAL,
  demandFrom,
  flowState,
  named,
  originalOrders,
  projectWithout,
  purchasesOf,
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
  /** The item's daily forecast, read as the brief reads it, so both name the same gap. */
  const demand = useState('recovery-prompt-forecast', () => ({
    key: '',
    forecast: null as ForecastCurrent | null,
  }))
  // Read once per store and item; the key is taken first so a second caller does not read again.
  watch(
    () =>
      s.storeId && mission.value?.sku_id && s.session?.recoveryCases
        ? [s.storeId, mission.value.sku_id].join(':')
        : '',
    async (key) => {
      if (!key || demand.value.key === key) return
      demand.value = { key, forecast: null }
      const [store, sku] = [s.storeId, mission.value!.sku_id]
      try {
        const value = await api<ForecastCurrent>(
          `/api/v1/stores/${encodeURIComponent(store)}/forecast` + query({ sku_id: sku }),
        )
        if (demand.value.key === key) demand.value = { key, forecast: value }
      } catch {}
    },
    { immediate: true },
  )
  async function load() {
    const store = s.storeId
    if (!store || !s.session?.recoveryCases) return
    try {
      const page = await api<{ items: RecoveryCase[] }>(
        '/api/v1/operations-cases' + query({ store_id: store }),
      )
      if (store !== s.storeId) return
      cache.value = { storeId: store, items: page.items }
      // Suppliers read in a restock's sourcing are named on this page too.
      for (const item of page.items)
        rememberSupplierNames((item.sourcing as Sourcing | null | undefined)?.suppliers || [])
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
      (c) => c.mission_id === m.id && !TERMINAL.includes(c.status),
    )
    if (!latest) return false
    const action = (latest.action_id && s.actions.find((a) => a.id === latest.action_id)) || null
    return !flowState({
      detail: latest,
      action,
      inbound: (action && s.inbounds.find((i) => i.action_id === action.id)) || null,
      originals: originalOrders(latest, s.inbounds),
      purchases: purchasesOf(latest, s.actions, s.inbounds),
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
  /**
   * The projected seven-day gap without a new purchase, as the solver settles it on the mission's
   * demand assumption: the same number the brief then writes ("不补的话 … 7 天共缺 N 件").
   */
  const gap = computed(() => {
    const clock = s.dashboard?.state.simulation_time
    const stock = shop.stock.value
    if (!clock || !stock || !mission.value) return null
    const forecast =
      demand.value.key === s.storeId + ':' + mission.value.sku_id ? demand.value.forecast : null
    const plan = demandFrom({
      forecast,
      plan: shop.plan.value,
      remainingDemand: stock.remaining_demand,
    })
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
  // One line says it all: the title opens with the reason ("常规方案买不了", "百川批发拒单了"), so
  // the card carries no tag repeating it.
  const title = computed(() => {
    const value = trigger.value
    if (!value) return ''
    const name = supplierDisplayName(value.supplier)
    const lead: Record<RecoveryReason, string> = {
      manual: '可以找别家应急补货',
      late: '原订单晚到',
      stockout: '常规方案补不上缺口',
      cash: '现金不够按原计划补货',
      infeasible: '常规方案买不了',
      failed: '这笔采购没有成功',
      declined: '{0}拒单了',
      partial: '{0}只能供应一部分',
    }
    const head = named(lead[value.reason], [name])
    // One measure of the gap everywhere: the seven days without any new purchase, as the brief
    // computes it ("不补的话"). The head therefore says why the regular plan is not enough, never
    // what is left after it (that would be a second measure in the same line).
    const short = gap.value ?? value.gap
    return short ? t('{0}：不补的话 7 天缺 {1} 件', [head, short]) : head
  })
  function launch() {
    const value = trigger.value
    if (!value || !mission.value) return null
    launcher.request({
      missionId: mission.value.id,
      reason: value.reason,
      exclude: value.reason === 'declined' ? value.supplier || null : null,
      gap: gap.value ?? value.gap,
    })
    return mission.value.id
  }
  return { load, trigger, shown, title, launch, underWay }
}
