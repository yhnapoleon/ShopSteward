<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import { named, outcomeOf, unbroken } from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 6, "结果": what the restock achieved, as the backend recorded when it settled the Case
// (shortages are the analysis's projection, so they read "预计"). A Case ended by hand has no
// outcome; it shows what was bought, if anything. When over, the card shows only this, as one
// line that opens on demand.
defineProps<{ compact?: boolean }>()
const emit = defineEmits<{ expand: [] }>()
const flow = useFlow()
const action = computed(() => flow.action.value)
const outcome = computed(() =>
  outcomeOf(
    flow.detail.value,
    flow.casePlan.value,
    action.value,
    flow.inbound.value,
    flow.cmp.value.wait,
  ),
)
const settled = computed(() => flow.detail.value?.status === 'RESOLVED')
const bought = computed(() => settled.value && outcome.value.path === 'purchase')
const waited = computed(() => settled.value && outcome.value.path === 'waiting')
const originalsIn = computed(() =>
  flow.originals.value.reduce((n, i) => n + i.received_quantity, 0),
)
// Waiting with no original order on the way was a decision not to restock.
const hadOriginals = computed(() => flow.originals.value.length > 0)
const names = computed(() =>
  outcome.value.suppliers.map((id) => supplierDisplayName(id)).join(tr('、')),
)
// One supplier that confirmed less than ordered; with several purchases the units add up per
// supplier instead (the backend's planned total is every order together).
const partial = computed(
  () =>
    outcome.value.parts.length < 2 &&
    outcome.value.planned != null &&
    outcome.value.ordered < outcome.value.planned,
)
/** "Baichuan Wholesale 10 + Anhe Trading 30" */
const parts = computed(() =>
  outcome.value.parts
    .map((p) => joinText([supplierDisplayName(p.supplierId), tr(p.quantity)], ' '))
    .join(' + '),
)
const change = computed(() =>
  outcome.value.before != null && outcome.value.after != null
    ? tr('预计缺货 {0} → {1} 件', [outcome.value.before, outcome.value.after])
    : '',
)
const title = computed(() =>
  tr(
    bought.value
      ? '应急补货完成'
      : waited.value && hadOriginals.value
        ? '已等到原订单'
        : '应急补货已结束',
  ),
)
/** Numbers stay with their units and "40 → 0 件" stays whole wherever the line wraps. */
const tight = (text: string) => unbroken(text).replace(/ → /g, '\u00a0→\u00a0')
const facts = computed(() => {
  const o = outcome.value
  if (bought.value)
    return [
      o.parts.length > 1
        ? tr('补到 {0} 件（{1}）', [o.received, parts.value])
        : partial.value
          ? named('{0}确认的 {1} 件已到货（订单 {2} 件）', [
              names.value,
              o.received,
              o.planned ?? 0,
            ])
          : named('{0} {1} 件已到货', [names.value, o.received]),
      change.value,
      tr('花了 {0}', [money(o.spend)]),
    ].filter(Boolean)
  if (waited.value)
    return [
      originalsIn.value ? tr('原订单 {0} 件已到', [originalsIn.value]) : tr('这次不补'),
      change.value,
    ].filter(Boolean)
  // Ended by hand: what was bought, if anything, and whether it is still on the way.
  if (action.value?.status === 'SUCCEEDED')
    return [
      o.ordered > o.received
        ? tr('{0} 件在途，货到后请登记', [o.ordered - o.received])
        : named('{0} {1} 件已到货', [names.value, o.received]),
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
    <span class="rf-summary-mark" :class="{ done: settled }" aria-hidden="true"
      ><AppIcon :name="settled ? 'check' : 'truck'"
    /></span>
    <b>{{ title }}</b>
    <span class="rf-summary-facts"
      ><span v-for="(fact, index) in facts" :key="index" class="rf-summary-fact">{{
        tight(fact)
      }}</span></span
    >
    <AppIcon name="chevron-down" />
  </button>
  <div v-else class="rf-stage rf-outcome">
    <h3 class="rf-title">{{ title }}</h3>
    <dl v-if="bought" class="rf-figures">
      <div>
        <dt>{{ tr('预计缺货') }}</dt>
        <dd>
          {{
            outcome.before != null && outcome.after != null
              ? tight(tr('{0} → {1} 件', [outcome.before, outcome.after]))
              : tr('尚未取得')
          }}
        </dd>
        <small>{{ tr('7 天合计（预计）') }}</small>
      </div>
      <div>
        <dt>{{ tr('花了') }}</dt>
        <dd>{{ tr(money(outcome.spend)) }}</dd>
        <small>{{ names }}</small>
      </div>
      <div>
        <dt>{{ tr('到货') }}</dt>
        <dd>{{ tight(tr('{0}/{1} 件', [outcome.received, outcome.ordered])) }}</dd>
        <small>{{
          partial
            ? tr('订单 {0} 件，供应商只确认了一部分', [outcome.planned ?? 0])
            : tr('已计入在库')
        }}</small>
      </div>
    </dl>
    <p v-else class="rf-sub">{{ tight(facts.join(' · ')) }}</p>
  </div>
</template>
