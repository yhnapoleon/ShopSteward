<script setup lang="ts">
import { t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import { isRecoveryPlan } from '~/utils/plans'
import { candidateDays, dayOf, named, priceOf } from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 3, "采用并确认": the adopted quote is a plan that waits for the owner's confirmation in
// the page's approval dialog. Confirming there reserves the cash and sends (or writes) the order.
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
 * A supplier read from documents has no ordering system, so the backend always leaves its order
 * to the owner (execution/repository.py). Any other order follows the deployment's
 * PURCHASE_CHANNEL, which the page cannot read, so the card says nothing about it.
 */
const byHand = computed(() =>
  flow.directory.readable.value.some((x) => x.supplier_id === purchase.value?.supplier_id),
)
const ready = computed(
  () => shop.plan.value?.id === plan.value?.id && shop.canDecide.value && !s.busy,
)
const waiting = computed(() =>
  s.dashboard?.freshness.status !== 'FRESH'
    ? tr('经营数据还在同步，同步后就能确认。')
    : shop.unresolved.value
      ? tr('另一笔采购还没处理完，处理完再确认这一笔。')
      : tr('经营情况刚有变化，正在核对这份方案。'),
)
</script>
<template>
  <div class="rf-stage rf-confirm">
    <h3 class="rf-title">
      {{
        purchase
          ? named('核对后确认：用{0}补 {1} 件', [name, purchase.quantity])
          : tr('正在读取应急方案')
      }}
    </h3>
    <dl v-if="purchase" class="rf-figures">
      <div>
        <dt>{{ tr('本次支出') }}</dt>
        <dd>{{ tr(money(purchase.total_minor)) }}</dd>
        <small>{{
          tr('{0} 件 × {1}', [purchase.quantity, priceOf(purchase.unit_price_minor)])
        }}</small>
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
            before == null
              ? tr('{0} 件', [chosen?.shortage_qty ?? 0])
              : tr('{0} → {1} 件', [before, chosen?.shortage_qty ?? 0])
          }}
        </dd>
        <small>{{ tr('7 天合计') }}</small>
      </div>
      <div>
        <dt>{{ tr('预计到货') }}</dt>
        <dd>{{ dayOf(purchase.expected_arrival_at) }}</dd>
        <small v-if="byHand">{{ tr('确认后由你把订单发给供应商') }}</small>
      </div>
    </dl>
    <RecoveryDays
      v-if="chosen"
      :days="candidateDays(chosen)"
      :label="named('用{0}补 {1} 件的七天', [name, chosen.quantity])"
    />
    <p v-if="!flow.approver.value" class="channel-note">
      {{ tr('确认采购需要审批权限；有权限的人打开这件事就能确认。') }}
    </p>
    <p v-else-if="purchase && !ready && !s.busy" class="notice" role="status">{{ waiting }}</p>
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
      ><button
        type="button"
        class="primary"
        :disabled="!ready || !flow.approver.value || !purchase"
        data-recovery-next
        @click="flow.confirm()"
      >
        {{ purchase ? tr('核对 {0} 件采购', [purchase.quantity]) : tr('正在读取…')
        }}<AppIcon name="arrow-right" />
      </button>
    </footer>
  </div>
</template>
