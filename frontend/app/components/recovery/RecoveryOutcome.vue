<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import { outcomeOf } from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 6, "结果": what the restock achieved. Shortages are the plan's projection (the backend
// records no observed outcome for a Case), so they read "预计". When the restock is over the card
// shows only this, as one line that opens on demand.
defineProps<{ compact?: boolean }>()
const emit = defineEmits<{ expand: [] }>()
const flow = useFlow()
const state = computed(() => flow.flow.value)
const action = computed(() => flow.action.value)
const outcome = computed(() =>
  outcomeOf(flow.casePlan.value, action.value, flow.inbound.value, flow.cmp.value.wait),
)
const bought = computed(() => action.value?.status === 'SUCCEEDED')
const arrived = computed(() => bought.value && state.value.stage === 'result')
const waited = computed(() => state.value.variant === 'wait' && state.value.stage === 'result')
const originalsIn = computed(() =>
  flow.originals.value.reduce((n, i) => n + i.received_quantity, 0),
)
// Waiting with no original order on the way was a decision not to restock.
const hadOriginals = computed(() => flow.originals.value.length > 0)
const title = computed(() =>
  tr(
    arrived.value
      ? '应急补货完成'
      : waited.value && hadOriginals.value
        ? '已等到原订单'
        : '应急补货已结束',
  ),
)
const facts = computed(() => {
  const o = outcome.value
  const name = supplierDisplayName(o.supplierId)
  if (arrived.value)
    return [
      tr('{0} {1} 件已到货', [name, o.received]),
      o.before != null && o.after != null ? tr('预计缺货 {0} → {1} 件', [o.before, o.after]) : '',
      tr('花了 {0}', [money(o.spend)]),
    ].filter(Boolean)
  if (waited.value)
    return [
      originalsIn.value ? tr('原订单 {0} 件已到', [originalsIn.value]) : tr('这次不补'),
      o.before != null ? tr('预计缺货 {0} 件', [o.before]) : '',
    ].filter(Boolean)
  if (bought.value)
    return [
      tr('{0} 件在途，货到后请登记', [o.ordered - o.received]),
      tr('花了 {0}', [money(o.spend)]),
    ]
  return [tr('没有补货')]
})
</script>
<template>
  <button
    v-if="compact"
    type="button"
    class="rf-summary"
    :aria-label="joinText([title, ...facts], tr('，'))"
    data-recovery-summary
    @click="emit('expand')"
  >
    <span class="rf-summary-mark" :class="{ done: arrived || waited }" aria-hidden="true"
      ><AppIcon :name="arrived || waited ? 'check' : 'truck'"
    /></span>
    <b>{{ title }}</b>
    <span class="rf-summary-facts">{{ facts.join(' · ') }}</span>
    <AppIcon name="chevron-down" />
  </button>
  <div v-else class="rf-stage rf-outcome">
    <h3 class="rf-title">{{ title }}</h3>
    <dl v-if="arrived" class="rf-figures">
      <div>
        <dt>{{ tr('预计缺货') }}</dt>
        <dd>
          {{
            outcome.before != null && outcome.after != null
              ? tr('{0} → {1} 件', [outcome.before, outcome.after])
              : tr('尚未取得')
          }}
        </dd>
        <small>{{ tr('7 天合计，按方案推演') }}</small>
      </div>
      <div>
        <dt>{{ tr('花了') }}</dt>
        <dd>{{ tr(money(outcome.spend)) }}</dd>
        <small>{{ supplierDisplayName(outcome.supplierId) }}</small>
      </div>
      <div>
        <dt>{{ tr('到货') }}</dt>
        <dd>{{ tr('{0}/{1} 件', [outcome.received, outcome.ordered]) }}</dd>
        <small>{{ tr('已计入在库') }}</small>
      </div>
    </dl>
    <p v-else class="rf-sub">{{ facts.join(' · ') }}</p>
  </div>
</template>
