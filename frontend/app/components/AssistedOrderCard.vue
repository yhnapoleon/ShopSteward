<script setup lang="ts">
// The system reaches no supplier: the owner sends this message and pastes the reply back.
import { joinText, locale, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
const shop = useShop()
const { s, awaitingSupplier, hasRole } = shop
const action = awaitingSupplier
const order = computed(() => action.value?.order_message || null)
const message = computed(() => order.value?.text[locale.value === 'en' ? 'en' : 'zh'] || '')
const reply = ref(''),
  error = ref(''),
  copied = ref(false),
  confirmingWithdrawal = ref(false)
const approver = computed(() => hasRole('approver'))
async function copy() {
  error.value = ''
  try {
    await navigator.clipboard.writeText(message.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 2500)
  } catch {
    error.value = '无法复制，请选中文字复制。'
  }
}
async function submit() {
  if (!action.value || !reply.value.trim()) return
  error.value = ''
  try {
    const updated = await shop.recordSupplierReply(action.value.id, reply.value.trim())
    // A reply that settles nothing stays visible below; the box is ready for the next one.
    if (updated) reply.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}
// A reply that confirms fewer units at the ordered price can be taken as it is.
const partial = computed(() =>
  action.value?.supplier_reply?.outcome === 'partial' ? action.value.supplier_reply : null,
)
async function acceptPartial() {
  if (!action.value) return
  error.value = ''
  try {
    await shop.acceptPartialSupply(action.value.id)
  } catch (e) {
    error.value = (e as Error).message
  }
}
async function withdraw() {
  if (!action.value) return
  error.value = ''
  try {
    await shop.withdrawOrder(action.value.id)
    confirmingWithdrawal.value = false
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>
<template>
  <article v-if="action && order" class="assisted-order glass" data-assisted-order>
    <span class="tag amber">{{ tr('待供应商确认') }}</span>
    <h2>{{ tr('把这份订单发给供应商') }}</h2>
    <p>
      {{
        tr(
          '订单信息已按你确认的方案生成。用你自己的微信或 WhatsApp 发给供应商；收到回复后粘贴到下面，系统会整理成回执。供应商回复前，订单保持待确认，资金暂时预留。',
        )
      }}
    </p>
    <div class="assisted-facts">
      <div>
        <span>{{ tr('供应商') }}</span
        ><b>{{ order.supplier_id }}</b>
      </div>
      <div>
        <span>{{ tr('数量') }}</span
        ><b>{{ joinText([tr(order.quantity), tr('件')]) }}</b>
      </div>
      <div>
        <span>{{ tr('单价') }}</span
        ><b>{{ tr(money(order.unit_price_minor)) }}</b>
      </div>
      <div>
        <span>{{ tr('合计') }}</span
        ><b>{{ tr(money(order.total_minor)) }}</b>
      </div>
      <div>
        <span>{{ tr('希望送达') }}</span
        ><b>{{ order.requested_delivery_date }}</b>
      </div>
    </div>
    <pre class="assisted-message" data-order-message>{{ message }}</pre>
    <div class="action-row">
      <span class="action-note">{{
        joinText([tr('订单编号'), order.reference])
      }}</span
      ><button class="secondary" type="button" @click="copy">
        {{ tr(copied ? '已复制' : '复制订单信息') }}
      </button>
    </div>
    <SupplierReceipt v-if="action.supplier_reply" :reply="action.supplier_reply" />
    <div v-if="partial" class="assisted-partial" data-partial-supply>
      <p>
        {{
          tr(
            '供应商只能供 {0} 件。按这个数量成交：只付这 {0} 件的钱，其余预留资金释放；缺的部分可以在供应异常应对里找别家补上。',
            [partial.quantity ?? ''],
          )
        }}
      </p>
      <button
        class="primary"
        type="button"
        :disabled="Boolean(s.busy) || !approver"
        data-accept-partial
        @click="acceptPartial"
      >
        {{ tr('按对方数量成交（{0} 件）', [partial.quantity ?? '']) }}
      </button>
    </div>
    <label class="assisted-reply"
      >{{ tr('粘贴供应商的回复')
      }}<textarea
        v-model="reply"
        maxlength="4000"
        :disabled="Boolean(s.busy) || !approver"
        :placeholder="tr('例如：收到，40件没问题，单价10元，周四送到。')"
        data-supplier-reply
      />
    </label>
    <p v-if="!approver" class="channel-note">
      {{ tr('当前身份可查看订单，登记供应商回复需要审批权限。') }}
    </p>
    <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
    <div class="action-row">
      <button
        v-if="!confirmingWithdrawal"
        class="text-link"
        type="button"
        :disabled="Boolean(s.busy) || !approver"
        @click="confirmingWithdrawal = true"
      >
        {{ tr('撤回这笔订单') }}</button
      ><span v-else class="assisted-withdraw"
        >{{ tr('撤回后预留资金释放，方案需要重新确认。')
        }}<button class="text-link" type="button" :disabled="Boolean(s.busy)" @click="withdraw">
          {{ tr('确认撤回') }}</button
        ><button class="text-link" type="button" @click="confirmingWithdrawal = false">
          {{ tr('先不撤回') }}
        </button></span
      ><button
        class="primary"
        type="button"
        :disabled="Boolean(s.busy) || !approver || !reply.trim()"
        @click="submit"
      >
        {{ tr(s.busy === '正在登记供应商回复' ? '正在读取回复…' : '登记回复') }}
      </button>
    </div>
  </article>
</template>
<style scoped>
.assisted-order {
  padding: 22px;
  display: grid;
  gap: 12px;
}
.assisted-order h2 {
  margin: 0;
}
.assisted-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px;
}
.assisted-facts div {
  display: grid;
  gap: 2px;
}
.assisted-facts span {
  font-size: 0.8rem;
  color: #607468;
}
.assisted-message {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  border: 1px solid #d4dbd6;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
  font: inherit;
  font-size: 0.92rem;
  margin: 0;
  user-select: all;
}
.assisted-reply {
  display: grid;
  gap: 6px;
  font-size: 0.9rem;
}
.assisted-reply textarea {
  min-height: 84px;
  resize: vertical;
  border: 1px solid #d4dbd6;
  border-radius: 10px;
  padding: 10px;
  background: #fff;
  color: #203b31;
  font: inherit;
}
.assisted-partial {
  display: grid;
  gap: 10px;
  justify-items: start;
  border: 1px solid #e3c98b;
  border-radius: 12px;
  padding: 12px 14px;
  background: #fffaf0;
}
.assisted-partial p {
  margin: 0;
}
.assisted-withdraw {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 0.85rem;
}
</style>
