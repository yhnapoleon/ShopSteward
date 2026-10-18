<script setup lang="ts">
import { t as tr } from '~/i18n'
import { supplierDisplayName } from '~/utils/glossary'
import { caseProblem, dayOf, named, unbroken } from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 5. An order the owner sent by hand: no source reports its goods, so the owner records them
// here ("货到后请登记"). An order sent through the supplier's system arrives by itself. When the
// owner chose to wait, this step watches the original orders instead.
const flow = useFlow()
const { s } = useShop()
const variant = computed(() => flow.flow.value.variant)
const action = computed(() => flow.action.value)
const inbound = computed(() => flow.inbound.value)
const name = computed(() => supplierDisplayName(action.value?.purchase_snapshot.supplier_id))
const outstanding = computed(() => inbound.value?.remaining_quantity ?? action.value?.quantity ?? 0)
const count = ref<number | null>(null)
watch(
  () => action.value?.id,
  () => (count.value = null),
)
const quantity = computed(() => count.value ?? outstanding.value)
const error = ref('')
const busy = computed(() => Boolean(flow.working.value || s.busy))
const arrival = computed(
  () =>
    inbound.value?.expected_arrival_at ||
    action.value?.supplier_reply?.delivery_date ||
    action.value?.purchase_snapshot.expected_arrival_at ||
    null,
)
const headline = computed(() => {
  if (variant.value === 'wait') return tr('等原订单到货')
  if (variant.value === 'direct') return named('等{0}送货', [name.value])
  if (inbound.value?.received_quantity)
    return tr('已到 {0}/{1} 件，剩下的到了再登记', [
      inbound.value.received_quantity,
      inbound.value.ordered_quantity,
    ])
  return named('{0}已确认 {1} 件，货到后请登记', [name.value, action.value?.quantity ?? 0])
})
async function record() {
  error.value = ''
  const value = quantity.value
  if (!Number.isInteger(value) || value < 1 || value > outstanding.value) {
    error.value = '到货数量要在 1 和未到数量之间。'
    return
  }
  if (await flow.arrive(value)) count.value = null
}
const failure = computed(() =>
  flow.problem.value ? caseProblem(flow.problem.value.code, flow.problem.value.message) : '',
)
</script>
<template>
  <div class="rf-stage rf-receive">
    <h3 class="rf-title" aria-live="polite">{{ unbroken(headline) }}</h3>
    <ul v-if="variant === 'wait'" class="rf-originals">
      <li v-for="item in flow.originals.value" :key="item.action_id">
        <b>{{ tr('原订单 {0} 件', [item.ordered_quantity]) }}</b>
        <span>{{
          item.remaining_quantity
            ? item.expected_arrival_at
              ? tr(item.is_overdue ? '预计 {0} 到 · 已超过预计时间' : '预计 {0} 到', [
                  dayOf(item.expected_arrival_at),
                ])
              : tr('到货时间待供应商确认')
            : tr('已到货')
        }}</span>
      </li>
    </ul>
    <dl v-else class="rf-figures rf-figures-compact">
      <div>
        <dt>{{ tr('预计到货') }}</dt>
        <dd>{{ dayOf(arrival) }}</dd>
      </div>
      <div>
        <dt>{{ tr('到货进度') }}</dt>
        <dd>
          {{
            tr('{0}/{1} 件', [
              inbound?.received_quantity ?? 0,
              inbound?.ordered_quantity ?? action?.quantity ?? 0,
            ])
          }}
        </dd>
      </div>
    </dl>
    <p v-if="variant === 'buy' && !flow.operator.value" class="channel-note">
      {{ tr('当前身份可查看订单，登记到货需要操作权限。') }}
    </p>
    <p v-if="error || failure" class="notice amber" role="alert">{{ tr(error) || failure }}</p>
    <footer class="rf-next">
      <span class="rf-links"
        ><button
          v-if="variant === 'wait' && flow.operator.value"
          type="button"
          class="text-link"
          :disabled="busy"
          @click="flow.again()"
        >
          {{ tr('改主意，找别家补') }}
        </button></span
      >
      <template v-if="variant === 'buy'">
        <label class="rf-count"
          >{{ tr('这次到了')
          }}<input
            type="number"
            min="1"
            :max="outstanding"
            :value="quantity"
            :disabled="busy || !flow.operator.value"
            data-arrival-quantity
            @input="count = Number(($event.target as HTMLInputElement).value)"
          />{{ tr('件') }}</label
        ><button
          type="button"
          class="primary"
          :disabled="busy || !flow.operator.value"
          data-recovery-next
          data-record-arrival
          @click="record"
        >
          {{ tr(flow.working.value === 'arrive' ? '正在登记…' : '登记到货')
          }}<AppIcon name="arrow-right" />
        </button>
      </template>
      <span v-else class="rf-quiet"
        ><AppIcon name="truck" />{{
          tr(variant === 'wait' ? '原订单到货后这里会更新' : '到货后自动入库，不需要你操作')
        }}</span
      >
    </footer>
  </div>
</template>
