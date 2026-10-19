<script setup lang="ts">
// No source reports the goods of an order the owner sent by hand: the owner records them here.
// The tag says what is expected of the owner, in the words the header and the order rows use.
import { t as tr } from '~/i18n'
import { supplierDisplayName } from '~/utils/glossary'
import { dayOf, named, unbroken } from '~/utils/recovery'
// Orders an emergency restock under way records in its own card are not listed here
// (useShop.awaitingArrival). `quiet`: another card (the restock, or a plan to confirm) holds the
// page's one primary action, so recording steps back.
defineProps<{ quiet?: boolean }>()
const shop = useShop()
const { s, awaitingArrival, hasRole } = shop
const arrivals = awaitingArrival
const operator = computed(() => hasRole('operator'))
const counts = reactive<Record<string, number>>({})
const error = ref('')
const counted = (id: string, outstanding: number) => counts[id] ?? outstanding
async function record(id: string, outstanding: number) {
  const quantity = counted(id, outstanding)
  error.value = ''
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > outstanding) {
    error.value = '到货数量要在 1 和未到数量之间。'
    return
  }
  try {
    await shop.recordArrival(id, quantity)
    delete counts[id]
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>
<template>
  <article
    v-for="{ action, inbound } in arrivals"
    :key="action.id"
    class="arrival-card glass"
    data-arrival-card
  >
    <span class="tag amber">{{ tr('货到后请登记') }}</span>
    <h2>
      {{
        unbroken(
          named('{0} {1} 件', [
            supplierDisplayName(action.purchase_snapshot.supplier_id),
            inbound.ordered_quantity,
          ]),
        )
      }}
    </h2>
    <dl class="arrival-facts">
      <div>
        <dt>{{ tr('预计到货') }}</dt>
        <dd>{{ dayOf(inbound.expected_arrival_at) }}</dd>
      </div>
      <div>
        <dt>{{ tr('到货进度') }}</dt>
        <dd>
          {{ unbroken(tr('{0}/{1} 件', [inbound.received_quantity, inbound.ordered_quantity])) }}
        </dd>
      </div>
    </dl>
    <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
    <div v-if="operator" class="action-row">
      <label class="arrival-count"
        >{{ tr('这次到了')
        }}<input
          type="number"
          min="1"
          :max="inbound.remaining_quantity"
          :value="counted(action.id, inbound.remaining_quantity)"
          :disabled="Boolean(s.busy)"
          data-arrival-quantity
          @input="counts[action.id] = Number(($event.target as HTMLInputElement).value)"
        />{{ tr('件') }}</label
      >
      <button
        :class="quiet ? 'secondary' : 'primary'"
        type="button"
        :disabled="Boolean(s.busy)"
        data-record-arrival
        @click="record(action.id, inbound.remaining_quantity)"
      >
        {{ tr(s.busy === '正在登记到货' ? '正在登记…' : '登记到货') }}
      </button>
    </div>
    <p v-else class="arrival-wait"><AppIcon name="user" />{{ tr('等有操作权限的人登记到货') }}</p>
  </article>
</template>
<style scoped>
.arrival-card {
  display: grid;
  gap: 12px;
  padding: 22px 26px 20px;
  border-radius: 26px;
}
.arrival-card > .tag {
  justify-self: start;
}
.arrival-card h2 {
  margin: 0;
  font-size: 26px;
  line-height: 1.38;
  letter-spacing: -0.6px;
  font-variant-numeric: tabular-nums;
}
.arrival-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, max-content));
  gap: 6px 40px;
  margin: 0;
}
.arrival-facts div {
  display: grid;
  gap: 2px;
}
.arrival-facts dt {
  font-size: 13px;
  color: #526477;
}
.arrival-facts dd {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  color: #28343e;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.arrival-card .action-row {
  margin-top: 4px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.arrival-count {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 14px;
  color: #3d566b;
}
.arrival-count input {
  width: 72px;
  min-height: 36px;
  border: 1px solid #cfddec;
  border-radius: 10px;
  padding: 6px 10px;
  background: #fff;
  color: #23394c;
  font: inherit;
  font-variant-numeric: tabular-nums;
}
.arrival-wait {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 7px;
  min-height: 46px;
  font-size: 13px;
  color: #5d7082;
}
.arrival-wait .icon {
  width: 15px;
  height: 15px;
  color: #7b93ab;
}
@media (max-width: 580px) {
  .arrival-card {
    padding: 18px 18px 16px;
    border-radius: 22px;
  }
  .arrival-card h2 {
    font-size: 22px;
  }
  .arrival-card .action-row {
    flex-wrap: wrap;
  }
  .arrival-card .action-row > button {
    flex: 1 1 100%;
  }
}
</style>
