<script setup lang="ts">
import { t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import { isRecoveryPlan } from '~/utils/plans'
import { dayOf, named, priceOf, unbroken } from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 3, "采用并确认": the adopted quote is a plan that waits for the owner's confirmation in
// the page's approval dialog. Confirming there reserves the cash and sends (or writes) the order.
// Who sends the order is said beside the button, the one moment it matters. Without the approval
// right the card waits for someone who has it: no disabled button, a status in its place.
const flow = useFlow()
const shop = useShop()
const { s } = shop
const plan = computed(() => flow.casePlan.value)
const chosen = computed(() => {
  const value = plan.value
  return value && isRecoveryPlan(value)
    ? value.candidates.find((c) => c.id === value.selected_candidate_id) || null
    : null
})
const before = computed(
  () => plan.value?.candidates.find((c) => c.quantity === 0)?.shortage_qty ?? null,
)
const purchase = computed(() => plan.value?.proposed_purchase || null)
const name = computed(() => supplierDisplayName(purchase.value?.supplier_id))
/**
 * Who sends the order (the flow knows it before confirming: a supplier read from documents always
 * gets it from the owner). When nothing tells, the card says nothing about it.
 */
const sender = computed(() =>
  flow.channel.value === 'assisted'
    ? named('确认后由你把订单发给{0}', [name.value])
    : flow.channel.value === 'direct'
      ? tr('确认后系统直接下单')
      : '',
)
const ready = computed(() => flow.canConfirm.value && !s.busy)
/** The plan is on its way to the page: the button says so; review opens by itself once it is in. */
const preparing = computed(
  () => !!purchase.value && !ready.value && (flow.preparing.value || !!s.busy),
)
/** Why it cannot be confirmed right now: said only while that holds, as its one cause. */
const waiting = computed(() => (preparing.value ? '' : flow.unavailableReason.value))
const tight = (text: string) => unbroken(text).replace(/ → /g, '\u00a0→\u00a0')
</script>
<template>
  <div class="rf-stage rf-confirm">
    <div class="rf-head-copy">
      <h3 class="rf-title">
        {{
          purchase
            ? tight(named('核对后确认：用{0}补 {1} 件', [name, purchase.quantity]))
            : tr('正在读取应急方案')
        }}
      </h3>
      <p v-if="purchase" class="rf-sub">
        {{
          tight(
            tr('{0} 件 × {1} · 预计 {2} 到', [
              purchase.quantity,
              priceOf(purchase.unit_price_minor),
              dayOf(purchase.expected_arrival_at),
            ]),
          )
        }}
      </p>
    </div>
    <RecoveryPurchases others />
    <dl v-if="purchase" class="rf-figures">
      <div>
        <dt>{{ tr('本次支出') }}</dt>
        <dd>{{ tr(money(purchase.total_minor)) }}</dd>
      </div>
      <div>
        <dt>{{ tr('采购后现金') }}</dt>
        <dd>{{ tr(money(chosen?.cash_after_minor)) }}</dd>
        <small>{{ tr('底线 {0}', [money(plan?.input_snapshot.policy.cash_floor_minor)]) }}</small>
      </div>
      <div>
        <dt>{{ tr('预计缺货') }}</dt>
        <dd>
          {{
            tight(
              before == null
                ? tr('{0} 件', [chosen?.shortage_qty ?? 0])
                : tr('{0} → {1} 件', [before, chosen?.shortage_qty ?? 0]),
            )
          }}
        </dd>
        <small>{{ tr('7 天合计') }}</small>
      </div>
    </dl>
    <p
      v-if="flow.approver.value && purchase && !ready && !s.busy && waiting"
      class="notice"
      role="status"
    >
      {{ waiting }}
    </p>
    <footer class="rf-next">
      <span class="rf-links"
        ><button
          v-if="flow.operator.value"
          type="button"
          class="text-link"
          @click="flow.revisiting.value = true"
        >
          {{ tr('换一家') }}</button
        ><button
          v-if="flow.operator.value"
          type="button"
          class="text-link"
          :disabled="Boolean(flow.working.value)"
          @click="flow.stop()"
        >
          {{ tr('结束这次应急补货') }}
        </button></span
      ><span v-if="!flow.approver.value" class="rf-quiet" data-recovery-waiting
        ><AppIcon name="user" />{{ tr('等有审批权限的人确认') }}</span
      ><template v-else
        ><span v-if="sender && purchase" class="rf-consequence">{{ sender }}</span
        ><button
          type="button"
          class="primary"
          :disabled="!ready || !purchase"
          data-recovery-next
          @click="flow.confirm()"
        >
          <RecoveryButtonLabel
            :label="
              purchase
                ? named('核对：用{0}补 {1} 件 · {2}', [
                    name,
                    purchase.quantity,
                    money(purchase.total_minor),
                  ])
                : tr('正在读取…')
            "
            :busy="tr('正在准备核对…')"
            :working="preparing"
          /></button
      ></template>
    </footer>
  </div>
</template>
