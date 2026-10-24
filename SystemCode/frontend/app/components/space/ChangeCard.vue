<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { api } from '~/utils/api'

// Why the plan changed between two versions: suggestion, remaining demand, what was already
// bought (kept) and the gap this version covers. Numbers come from the two stored plans.
const shop = useShop()
const { s, plan } = shop
const space = useSpace()
const { mission, executed } = space
// The two plans compared. A new version replaces the pair once its predecessor is read, so the
// card never empties in between; another mission or a first version clears it.
const change = ref<{ from: Schema<'Plan'>; to: Schema<'Plan'> } | null>(null)
const error = ref('')
// Only a version that arrives while the page is open slides in; opening the page does not.
const live = ref(false)
let epoch = 0
async function load() {
  const n = ++epoch,
    id = mission.value?.id,
    current = plan.value
  error.value = ''
  if (!id || !current || current.mission_id !== id || current.plan_version <= 1) {
    change.value = null
    return
  }
  if (change.value?.to.mission_id !== id) change.value = null
  // A version that replaced the one on the page: its predecessor is already here, so the card
  // turns over together with the plan card instead of one request later.
  const replaced = s.planChange
  if (
    replaced?.to.id === current.id &&
    replaced.from.mission_id === id &&
    replaced.from.plan_version === current.plan_version - 1
  ) {
    change.value = { from: replaced.from, to: current }
    return
  }
  try {
    const page = await api<Schema<'PlanList'>>(`/api/v1/missions/${id}/plans?limit=2`)
    if (n !== epoch || plan.value?.id !== current.id) return
    const previous = page.items.some((p) => p.id === current.id)
      ? page.items.find((p) => p.mission_id === id && p.plan_version === current.plan_version - 1)
      : undefined
    change.value = previous ? { from: previous, to: current } : null
  } catch {
    if (n !== epoch) return
    change.value = null
    error.value = '暂未取得前一版方案，可重试核对版本变化。'
  }
}
watch(
  [() => mission.value?.id, () => plan.value?.id],
  async (next, before) => {
    live.value = !!before?.[1] && next[0] === before[0] && next[1] !== before[1]
    await load()
  },
  { immediate: true },
)
onUnmounted(() => epoch++)
// Ledger entries between the two plans' inputs (by state version) say what triggered it.
const reason = computed(() => {
  const c = change.value
  if (!c) return ''
  const sku = mission.value?.sku_id
  const entries = s.ledger.filter(
    (e) =>
      e.state_version > c.from.state_version &&
      e.state_version <= c.to.state_version &&
      (!e.sku_id || e.sku_id === sku),
  )
  const triggers: [string, string][] = [
    ['DEMAND_REVISED', '需求修订'],
    ['GOODS_RECEIVED', '到货'],
    ['SALE_RECORDED', '销售入账'],
    ['PURCHASE_ACCEPTED', '采购受理'],
  ]
  const words = triggers
    .filter(([type]) => entries.some((e) => e.effect_type === type))
    .map(([, word]) => tr(word))
  const limit = (p: Schema<'Plan'>) => p.input_snapshot.task_constraints?.max_purchase_qty
  if (!words.length && limit(c.to) !== limit(c.from)) words.push(tr('你调整了采购数量'))
  return words.length ? words.join(tr('、')) : tr('依据更新')
})
const quantity = (p: Schema<'Plan'>) => p.proposed_purchase?.quantity ?? 0
const demand = (p: Schema<'Plan'>) => p.input_snapshot.forecast.remaining_demand
// A re-check that changed neither the suggestion nor the demand is noted in one quiet line
// instead of the receipt card.
const material = computed(
  () =>
    !!change.value &&
    (quantity(change.value.from) !== quantity(change.value.to) ||
      demand(change.value.from) !== demand(change.value.to)),
)
// The shortage with no purchase now: what this version still has to cover.
const gap = computed(() => {
  const to = change.value?.to
  return to ? (to.candidates.find((c) => c.quantity === 0)?.shortage_qty ?? quantity(to)) : 0
})
// How much of that gap the suggested purchase covers. A plan held back (by the cash floor, say)
// covers only part of it, and the row says "20/40", never that this round fills all 40.
const covered = computed(() => {
  const to = change.value?.to
  const after = to?.candidates.find((c) => c.quantity === quantity(to))?.shortage_qty
  return after == null ? gap.value : Math.max(0, gap.value - after)
})
</script>
<template>
  <p v-if="error" class="notice amber" role="status">
    {{ tr(error) }}<button class="text-link" @click="load">{{ tr('重试读取') }}</button>
  </p>
  <Transition :name="live ? 'space-rise' : 'space-still'" mode="out-in">
    <section
      v-if="change && material"
      :key="change.to.id"
      class="plan-change-receipt space-change"
      :aria-label="tr('方案变化')"
    >
      <AppIcon name="check-check" />
      <div class="space-change-body">
        <b>{{ tr('方案更新了 · {0}', [reason]) }}</b>
        <dl class="space-change-grid">
          <div v-if="quantity(change.from) !== quantity(change.to)">
            <dt>{{ tr('建议补货') }}</dt>
            <dd>
              {{
                joinText([tr(quantity(change.from)), '→', tr(quantity(change.to)), tr('件')], ' ')
              }}
            </dd>
          </div>
          <div v-if="demand(change.from) !== demand(change.to)">
            <dt>{{ tr('剩余需求') }}</dt>
            <dd>
              {{ joinText([tr(demand(change.from)), '→', tr(demand(change.to)), tr('件')], ' ') }}
            </dd>
          </div>
          <div v-if="executed">
            <dt>{{ tr('已执行采购') }}</dt>
            <dd>{{ tr('{0} 件 · 保留', [executed]) }}</dd>
          </div>
          <div v-if="gap">
            <dt>{{ tr('这次只补缺口') }}</dt>
            <dd>
              {{ covered < gap ? tr('{0}/{1} 件', [covered, gap]) : tr('{0} 件', [gap]) }}
            </dd>
          </div>
        </dl>
      </div>
    </section>
    <p v-else-if="change" :key="'same-' + change.to.id" class="source-note space-change-quiet">
      <AppIcon name="check" />{{ tr('方案重新核对过 · {0}', [reason]) }} ·
      {{ tr('建议数量和剩余需求都没有变化。') }}
    </p>
  </Transition>
</template>
