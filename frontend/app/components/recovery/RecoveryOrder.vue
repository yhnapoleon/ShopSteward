<script setup lang="ts">
import { locale, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import { caseProblem, dayOf, named, priceOf, unbroken } from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 4, "发单并登记回复": the system reaches no supplier. The owner sends the order message
// through their own channel and pastes the reply back; it becomes the receipt, or the order keeps
// waiting with the reason. Before any reply the message is the page; once a reply is in, the
// message folds to one line and the reply box waits behind "登记新回复". When the supplier can
// supply only part, taking that part is the main action, and its cost is said right above it.
const flow = useFlow()
const { s } = useShop()
const action = computed(() => flow.action.value)
const order = computed(() => action.value?.order_message || null)
const message = computed(() => order.value?.text[locale.value === 'en' ? 'en' : 'zh'] || '')
const name = computed(() => supplierDisplayName(action.value?.purchase_snapshot.supplier_id))
const system = computed(() => flow.flow.value.actor === 'system')
/** The supplier can give only part, still to decide (once taken, the comparison shows it). */
const partial = computed(() => {
  const value = flow.partial.value
  return value && !value.taken ? value : null
})
const unclear = computed(() => action.value?.supplier_reply?.outcome === 'needs_attention')
const replied = computed(() => !!action.value?.supplier_reply)
const reply = ref(''),
  copied = ref(false),
  copyError = ref(''),
  withdrawing = ref(false),
  writing = ref(false)
watch(
  () => action.value?.id,
  () => (writing.value = false),
)
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
/** One line of facts under the title: the order, or what the supplier offered against it. */
const facts = computed(() => {
  const o = order.value
  if (!o) return ''
  if (partial.value)
    return tr('订单 {0} 件 · 对方给 {1} 件', [partial.value.ordered, partial.value.offered])
  return tr('{0} 件 × {1} · 合计 {2} · 希望 {3} 送达', [
    o.quantity,
    priceOf(o.unit_price_minor),
    money(o.total_minor),
    dayOf(o.requested_delivery_date),
  ])
})
const consequence = computed(() =>
  partial.value
    ? tr('只付 {0}，余下 {1} 释放；还缺 {2} 件，之后可以找别家补。', [
        money(partial.value.payMinor),
        money(partial.value.releaseMinor),
        partial.value.missing,
      ])
    : '',
)
/** The reply box: open by itself, except beside a partial offer, where it waits behind a link. */
const boxOpen = computed(() => !partial.value || writing.value)
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
  if (result) {
    reply.value = ''
    writing.value = false
  }
}
async function withdraw() {
  await flow.withdraw()
  withdrawing.value = false
}
const failure = computed(() =>
  flow.problem.value ? caseProblem(flow.problem.value.code, flow.problem.value.message) : '',
)
const tight = (text: string) => unbroken(text).replace(/ → /g, '\u00a0→\u00a0')
/** A price as people write it in a reply: "9.50", no currency. */
const decimal = (minor: number) => (minor / 100).toFixed(2)
</script>
<template>
  <div class="rf-stage rf-order">
    <div class="rf-head-copy">
      <h3 class="rf-title" aria-live="polite">{{ tight(headline) }}</h3>
      <p v-if="facts && !system" class="rf-sub">{{ tight(facts) }}</p>
    </div>
    <p v-if="action?.status === 'UNKNOWN'" class="notice amber">
      {{ tr('这笔采购的结果还在确认，预留的钱和订单都保留着；确认前不要另下一单。') }}
    </p>
    <RecoveryPurchases others />
    <template v-if="order && !system">
      <!-- Before a reply: the message to send, exactly as it will be copied. -->
      <div v-if="!replied" class="rf-message">
        <pre data-order-message>{{ message }}</pre>
        <button type="button" class="secondary rf-copy" @click="copy">
          <AppIcon :name="copied ? 'check' : 'file-text'" />{{ tr(copied ? '已复制' : '复制') }}
        </button>
      </div>
      <!-- After a reply: the message is sent; it opens on demand. -->
      <div v-else class="rf-sent">
        <details>
          <summary>
            <AppIcon name="check" />{{ tr('订单已发') }}<AppIcon name="chevron-down" />
          </summary>
          <pre data-order-message>{{ message }}</pre>
        </details>
        <button type="button" class="text-link rf-sent-copy" @click="copy">
          {{ tr(copied ? '已复制' : '复制') }}
        </button>
      </div>
      <p v-if="copyError" class="notice amber" role="alert">{{ tr(copyError) }}</p>
      <SupplierReceipt v-if="action?.supplier_reply" :reply="action.supplier_reply" />
      <template v-if="flow.approver.value">
        <button
          v-if="!boxOpen"
          type="button"
          class="text-link rf-reply-open"
          data-recovery-new-reply
          @click="writing = true"
        >
          <AppIcon name="plus" />{{ tr('登记新回复') }}
        </button>
        <div v-else class="rf-reply">
          <label class="rf-field rf-field-wide"
            >{{ tr(replied ? '粘贴新的回复' : '粘贴供应商的回复')
            }}<textarea
              v-model="reply"
              rows="3"
              maxlength="4000"
              :disabled="busy"
              :placeholder="
                tr('例如：好嘞，{0} 件没问题，{1} 一件，明天到。', [
                  order.quantity,
                  decimal(order.unit_price_minor),
                ])
              "
              data-supplier-reply
            />
          </label>
          <!-- With the reply box open beside another main action, sending the reply is secondary. -->
          <span v-if="partial" class="rf-reply-actions"
            ><button
              type="button"
              class="secondary"
              :disabled="busy || !reply.trim()"
              data-recovery-submit-reply
              @click="submit"
            >
              {{ tr(flow.working.value === 'reply' ? '正在读取回复…' : '登记回复') }}</button
            ><button type="button" class="text-link" @click="writing = false">
              {{ tr('收起') }}
            </button></span
          >
        </div>
      </template>
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
          {{ tr('撤回这笔订单…') }}</button
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
      ><span v-else-if="order && partial && flow.approver.value" class="rf-links"
        ><button
          type="button"
          class="text-link"
          :disabled="busy"
          data-recovery-switch
          @click="flow.withdrawAndSwitch()"
        >
          {{ tr('撤回整单，找别家补 {0} 件', [partial.ordered]) }}
        </button></span
      ><span v-else class="rf-links" />
      <span v-if="system" class="rf-quiet"
        ><AppIcon name="orbit" />{{ tr('不需要你操作，结果回来后这里会更新') }}</span
      >
      <span v-else-if="order && !flow.approver.value" class="rf-quiet"
        ><AppIcon name="user" />{{ tr('等有审批权限的人登记回复') }}</span
      >
      <template v-else-if="order">
        <template v-if="partial">
          <p class="rf-consequence is-above">{{ tight(consequence) }}</p>
          <button
            type="button"
            class="primary"
            :disabled="busy"
            data-recovery-next
            data-accept-partial
            @click="flow.acceptPartial()"
          >
            <RecoveryButtonLabel
              :label="tr('按对方数量成交（{0} 件）', [partial.offered])"
              :busy="tr('正在成交…')"
              :working="flow.working.value === 'accept'"
            />
          </button>
        </template>
        <button
          v-else
          type="button"
          class="primary"
          :disabled="busy || !reply.trim()"
          data-recovery-next
          @click="submit"
        >
          <RecoveryButtonLabel
            :label="tr('登记回复')"
            :busy="tr('正在读取回复…')"
            :working="flow.working.value === 'reply'"
          />
        </button>
      </template>
    </footer>
  </div>
</template>
