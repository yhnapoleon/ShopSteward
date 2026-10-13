<script setup lang="ts">
// No source reports the goods of an order the owner sent by hand: the owner records them here.
import { joinText, t as tr } from '~/i18n'
import { when } from '~/utils/presentation'
const shop = useShop()
const { s, awaitingArrival, hasRole } = shop
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
    v-for="{ action, inbound } in awaitingArrival"
    :key="action.id"
    class="arrival-card glass"
    data-arrival-card
  >
    <span class="tag amber">{{ tr('等待到货') }}</span>
    <h2>{{ tr('货到后在这里登记') }}</h2>
    <p>
      {{
        tr(
          '这笔订单是你自己发给供应商的，系统收不到到货通知。货到店后登记数量，库存才会更新。',
        )
      }}
    </p>
    <div class="arrival-facts">
      <div>
        <span>{{ tr('供应商') }}</span
        ><b>{{ action.purchase_snapshot.supplier_id }}</b>
      </div>
      <div>
        <span>{{ tr('到货进度') }}</span
        ><b>{{
          joinText([
            tr(inbound.received_quantity),
            '/',
            tr(inbound.ordered_quantity),
            tr('件已到货'),
          ])
        }}</b>
      </div>
      <div>
        <span>{{ tr('预计到货') }}</span
        ><b>{{ tr(when(inbound.expected_arrival_at)) }}</b>
      </div>
    </div>
    <p v-if="!operator" class="channel-note">
      {{ tr('当前身份可查看订单，登记到货需要操作权限。') }}
    </p>
    <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
    <div class="action-row">
      <label class="arrival-count"
        >{{ tr('本次到货件数')
        }}<input
          type="number"
          min="1"
          :max="inbound.remaining_quantity"
          :value="counted(action.id, inbound.remaining_quantity)"
          :disabled="Boolean(s.busy) || !operator"
          data-arrival-quantity
          @input="counts[action.id] = Number(($event.target as HTMLInputElement).value)"
      /></label>
      <button
        class="primary"
        type="button"
        :disabled="Boolean(s.busy) || !operator"
        data-record-arrival
        @click="record(action.id, inbound.remaining_quantity)"
      >
        {{ tr(s.busy === '正在登记到货' ? '正在登记…' : '登记到货') }}
      </button>
    </div>
  </article>
</template>
<style scoped>
.arrival-card {
  padding: 22px;
  display: grid;
  gap: 12px;
}
.arrival-card h2 {
  margin: 0;
}
.arrival-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px;
}
.arrival-facts div {
  display: grid;
  gap: 2px;
}
.arrival-facts span {
  font-size: 0.8rem;
  color: #607468;
}
.arrival-count {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 0.9rem;
}
.arrival-count input {
  width: 88px;
  border: 1px solid #d4dbd6;
  border-radius: 10px;
  padding: 8px 10px;
  background: #fff;
  color: #203b31;
  font: inherit;
}
</style>
