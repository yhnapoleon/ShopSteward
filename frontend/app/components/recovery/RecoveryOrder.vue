<script setup lang="ts">
import { joinText, locale, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import { caseProblem, dayOf, named, partialReply, priceOf, unbroken } from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 4, "发单并登记回复": the system reaches no supplier. The owner sends the order message
// through their own channel and pastes the reply back; it becomes the receipt, or the order keeps
// waiting with the reason. When the supplier can supply only part, the owner can take the order
// back and compare the other suppliers (the backend cannot accept part of an order).
const flow = useFlow()
const { s } = useShop()
const action = computed(() => flow.action.value)
const order = computed(() => action.value?.order_message || null)
const message = computed(() => order.value?.text[locale.value === 'en' ? 'en' : 'zh'] || '')
const name = computed(() => supplierDisplayName(action.value?.purchase_snapshot.supplier_id))
const system = computed(() => flow.flow.value.actor === 'system')
const partial = computed(() => partialReply(action.value))
const unclear = computed(() => action.value?.supplier_reply?.outcome === 'needs_attention')
const reply = ref(''),
  copied = ref(false),
  copyError = ref(''),
  withdrawing = ref(false)
const busy = computed(() => Boolean(flow.working.value || s.busy))
const headline = computed(() => {
  const a = action.value
  if (!a) return tr('正在读取订单')
  if (a.status === 'UNKNOWN') return tr('采购结果还没有核实')
  if (a.channel !== 'assisted') return named('正在向{0}下单，等对方回执', [name.value])
  if (a.status === 'QUEUED') return named('正在生成给{0}的订单信息', [name.value])
  if (partial.value)
    return named('{0}只能给 {1} 件，订单是 {2} 件', [
      name.value,
      partial.value.offered,
      partial.value.ordered,
    ])
  if (unclear.value) return named('{0}的回复还不能确认这笔订单', [name.value])
  return named('把订单发给{0}，收到回复后贴回来', [name.value])
})
let copiedTimer: ReturnType<typeof setTimeout> | undefined
async function copy() {
  copyError.value = ''
  try {
    await navigator.clipboard.writeText(message.value)
    copied.value = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => (copied.value = false), 2400)
  } catch {
    copyError.value = '无法复制，请选中文字复制。'
  }
}
onUnmounted(() => clearTimeout(copiedTimer))
async function submit() {
  const text = reply.value.trim()
  if (!text) return
  const result = await flow.reply(text)
  // A reply that settles nothing stays visible as the receipt; the box is ready for the next one.
  if (result) reply.value = ''
}
async function withdraw() {
  await flow.withdraw()
  withdrawing.value = false
}
const failure = computed(() =>
  flow.problem.value ? caseProblem(flow.problem.value.code, flow.problem.value.message) : '',
)
</script>
<template>
  <div class="rf-stage rf-order">
    <h3 class="rf-title" aria-live="polite">{{ unbroken(headline) }}</h3>
    <p v-if="action?.status === 'UNKNOWN'" class="notice amber">
      {{ tr('后台正在核实原采购。不要用新采购代替查询，预留资金与原订单仍保留。') }}
    </p>
    <template v-if="order && !system">
      <dl class="rf-figures rf-figures-compact">
        <div>
          <dt>{{ tr('数量') }}</dt>
          <dd>{{ tr('{0} 件', [order.quantity]) }}</dd>
        </div>
        <div>
          <dt>{{ tr('单价') }}</dt>
          <dd>{{ priceOf(order.unit_price_minor) }}</dd>
        </div>
        <div>
          <dt>{{ tr('合计') }}</dt>
          <dd>{{ tr(money(order.total_minor)) }}</dd>
        </div>
        <div>
          <dt>{{ tr('希望送达') }}</dt>
          <dd>{{ dayOf(order.requested_delivery_date) }}</dd>
        </div>
      </dl>
      <div class="rf-message">
        <div class="rf-message-head">
          <span>{{ joinText([tr('订单编号'), order.reference], ' ') }}</span
          ><button type="button" class="secondary rf-copy" @click="copy">
            <AppIcon :name="copied ? 'check' : 'file-text'" />{{
              tr(copied ? '已复制' : '复制订单信息')
            }}
          </button>
        </div>
        <pre data-order-message>{{ message }}</pre>
      </div>
      <p v-if="copyError" class="notice amber" role="alert">{{ tr(copyError) }}</p>
      <SupplierReceipt v-if="action?.supplier_reply" :reply="action.supplier_reply" />
      <label class="rf-field rf-field-wide"
        >{{ tr(action?.supplier_reply ? '粘贴新的回复' : '粘贴供应商的回复')
        }}<textarea
          v-model="reply"
          rows="3"
          maxlength="4000"
          :disabled="busy || !flow.approver.value"
          :placeholder="
            tr('例如：收到，{0}件没问题，单价{1}元，周四送到。', [
              order.quantity,
              (order.unit_price_minor / 100).toFixed(2),
            ])
          "
          data-supplier-reply
        />
      </label>
      <p v-if="!flow.approver.value" class="channel-note">
        {{ tr('当前身份可查看订单，登记供应商回复和撤回订单需要审批权限。') }}
      </p>
    </template>
    <p v-if="failure" class="notice amber" role="alert">{{ failure }}</p>
    <footer class="rf-next">
      <span v-if="order && !system && !partial && flow.approver.value" class="rf-links"
        ><button
          v-if="!withdrawing"
          type="button"
          class="text-link"
          :disabled="busy"
          @click="withdrawing = true"
        >
          {{ tr('撤回这单…') }}</button
        ><span v-else class="rf-withdraw"
          >{{ tr('撤回后预留资金释放。')
          }}<button
            type="button"
            class="text-link"
            :disabled="busy"
            data-recovery-withdraw
            @click="withdraw"
          >
            {{ tr('确认撤回') }}</button
          ><button type="button" class="text-link" @click="withdrawing = false">
            {{ tr('先不撤回') }}
          </button></span
        ></span
      ><span v-else class="rf-links" />
      <span v-if="system" class="rf-quiet"
        ><AppIcon name="orbit" />{{ tr('不需要你操作，结果回来后这里会更新') }}</span
      >
      <template v-else-if="order">
        <button
          v-if="partial"
          type="button"
          class="secondary"
          :disabled="busy || !reply.trim() || !flow.approver.value"
          @click="submit"
        >
          {{ tr('登记新回复') }}
        </button>
        <button
          v-if="partial"
          type="button"
          class="primary"
          :disabled="busy || !flow.approver.value"
          data-recovery-next
          data-recovery-switch
          @click="flow.withdrawAndSwitch()"
        >
          {{ tr('撤回这单，找别家补 {0} 件', [partial.ordered]) }}<AppIcon name="arrow-right" />
        </button>
        <button
          v-else
          type="button"
          class="primary"
          :disabled="busy || !reply.trim() || !flow.approver.value"
          data-recovery-next
          @click="submit"
        >
          {{ tr(flow.working.value === 'reply' ? '正在读取回复…' : '登记回复')
          }}<AppIcon name="arrow-right" />
        </button>
      </template>
    </footer>
  </div>
</template>
