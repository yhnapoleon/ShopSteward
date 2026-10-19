<script setup lang="ts">
// The system reaches no supplier: the owner sends this message and pastes the reply back.
import { locale, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import { dayOf, named, partialReply, priceOf, unbroken } from '~/utils/recovery'
// `quiet`: an emergency restock leads the page and holds its one primary action, so this order's
// own steps step back to second buttons.
defineProps<{ quiet?: boolean }>()
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
// The supplier can supply only part of it. The owner takes that part as it is (only it is paid
// for); taking the whole order back and comparing other suppliers stays a second way (§18).
const launcher = useRecoveryLaunch()
const partial = computed(() => partialReply(action.value))
const supplier = computed(() => supplierDisplayName(order.value?.supplier_id))
/** Said right above the button that takes the part: what is paid, released and still missing. */
const consequence = computed(() => {
  const a = action.value
  const p = partial.value
  if (!a || !p) return ''
  const pay = p.offered * a.purchase_snapshot.unit_price_minor
  return tr('只付 {0}，余下 {1} 释放；还缺 {2} 件。', [
    money(pay),
    money(Math.max(0, a.amount_minor - pay)),
    p.ordered - p.offered,
  ])
})
const canSwitch = computed(
  () =>
    !!partial.value &&
    !!s.session?.recoveryCases &&
    approver.value &&
    hasRole('operator') &&
    !launcher.inProgress(action.value?.mission_id),
)
async function switchSupplier() {
  const order = action.value
  if (!order) return
  error.value = ''
  try {
    await shop.withdrawOrder(order.id)
    launcher.request({
      missionId: order.mission_id,
      reason: 'partial',
      exclude: order.purchase_snapshot.supplier_id,
    })
  } catch (e) {
    error.value = (e as Error).message
  }
}
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
    <h2>
      {{
        unbroken(
          partial
            ? named('{0}只能给 {1} 件，订单是 {2} 件', [supplier, partial.offered, partial.ordered])
            : named('把订单发给{0}，收到回复后贴回来', [supplier]),
        )
      }}
    </h2>
    <p class="assisted-facts">
      {{
        unbroken(
          tr('{0} 件 × {1} · 合计 {2} · 希望 {3} 送达', [
            order.quantity,
            priceOf(order.unit_price_minor),
            money(order.total_minor),
            dayOf(order.requested_delivery_date),
          ]),
        )
      }}
    </p>
    <div class="assisted-message">
      <pre data-order-message>{{ message }}</pre>
      <button class="secondary assisted-copy" type="button" @click="copy">
        <AppIcon :name="copied ? 'check' : 'file-text'" />{{ tr(copied ? '已复制' : '复制') }}
      </button>
    </div>
    <SupplierReceipt v-if="action.supplier_reply" :reply="action.supplier_reply" />
    <label class="assisted-reply"
      >{{ tr(action.supplier_reply ? '粘贴新的回复' : '粘贴供应商的回复')
      }}<textarea
        v-model="reply"
        maxlength="4000"
        :disabled="Boolean(s.busy) || !approver"
        :placeholder="tr('例如：收到，{0}件没问题，周四送到。', [order.quantity])"
        data-supplier-reply
      />
    </label>
    <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
    <div v-if="partial && approver" class="assisted-next" data-partial-supply>
      <p class="assisted-consequence">{{ unbroken(consequence) }}</p>
      <div class="action-row">
        <span class="assisted-links"
          ><button
            v-if="canSwitch"
            class="text-link"
            type="button"
            :disabled="Boolean(s.busy)"
            data-recovery-switch
            @click="switchSupplier"
          >
            {{ tr('撤回整单，找别家补 {0} 件', [partial.ordered]) }}</button
          ><template v-else
            ><button
              v-if="!confirmingWithdrawal"
              class="text-link"
              type="button"
              :disabled="Boolean(s.busy)"
              @click="confirmingWithdrawal = true"
            >
              {{ tr('撤回这笔订单') }}</button
            ><span v-else class="assisted-withdraw"
              >{{ tr('撤回后预留资金释放，方案需要重新确认。')
              }}<button
                class="text-link"
                type="button"
                :disabled="Boolean(s.busy)"
                @click="withdraw"
              >
                {{ tr('确认撤回') }}</button
              ><button class="text-link" type="button" @click="confirmingWithdrawal = false">
                {{ tr('先不撤回') }}
              </button></span
            ></template
          ><button
            class="text-link"
            type="button"
            :disabled="Boolean(s.busy) || !reply.trim()"
            @click="submit"
          >
            {{ tr(s.busy === '正在登记供应商回复' ? '正在读取回复…' : '登记新回复') }}
          </button></span
        ><button
          :class="quiet ? 'secondary' : 'primary'"
          type="button"
          :disabled="Boolean(s.busy)"
          data-accept-partial
          @click="acceptPartial"
        >
          {{ tr('按对方数量成交（{0} 件）', [partial.offered]) }}
        </button>
      </div>
    </div>
    <div v-else-if="approver" class="action-row">
      <span class="assisted-links"
        ><button
          v-if="!confirmingWithdrawal"
          class="text-link"
          type="button"
          :disabled="Boolean(s.busy)"
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
        ></span
      ><button
        :class="quiet ? 'secondary' : 'primary'"
        type="button"
        :disabled="Boolean(s.busy) || !reply.trim()"
        @click="submit"
      >
        {{ tr(s.busy === '正在登记供应商回复' ? '正在读取回复…' : '登记回复') }}
      </button>
    </div>
    <p v-else class="assisted-wait"><AppIcon name="user" />{{ tr('等有审批权限的人登记回复') }}</p>
  </article>
</template>
<style scoped>
.assisted-order {
  display: grid;
  gap: 12px;
  padding: 22px 26px 20px;
  border-radius: 26px;
}
.assisted-order > .tag {
  justify-self: start;
}
.assisted-order h2 {
  margin: 0;
  font-size: 26px;
  line-height: 1.38;
  letter-spacing: -0.6px;
  font-variant-numeric: tabular-nums;
  text-wrap: pretty;
}
.assisted-facts {
  margin: -4px 0 0;
  font-size: 14px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.assisted-message {
  position: relative;
  border: 1px solid #dde5ee;
  border-radius: 14px;
  background: #fff;
}
.assisted-message pre {
  margin: 0;
  padding: 14px 104px 14px 16px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: inherit;
  font-size: 14px;
  line-height: 1.75;
  color: #2b4256;
  user-select: all;
}
.assisted-copy.secondary {
  position: absolute;
  top: 8px;
  right: 8px;
  min-height: 34px;
  padding: 5px 12px;
  border-radius: 10px;
  font-size: 13px;
  gap: 6px;
}
.assisted-copy .icon {
  width: 14px;
  height: 14px;
}
.assisted-reply {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: #42617a;
}
.assisted-reply textarea {
  min-height: 84px;
  resize: vertical;
  border: 1px solid #cfddec;
  border-radius: 12px;
  padding: 10px 12px;
  background: #fff;
  color: #23394c;
  font: inherit;
  font-size: 15px;
  line-height: 1.6;
}
.assisted-order .action-row {
  margin-top: 4px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  flex-wrap: wrap;
}
.assisted-next {
  display: grid;
  gap: 0;
}
.assisted-consequence {
  margin: 0 0 -6px;
  font-size: 13px;
  color: #4f6478;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.assisted-links {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 18px;
  margin-right: auto;
}
.assisted-withdraw {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 13px;
  color: #6b5730;
}
.assisted-wait {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 7px;
  min-height: 46px;
  font-size: 13px;
  color: #5d7082;
}
.assisted-wait .icon {
  width: 15px;
  height: 15px;
  color: #7b93ab;
}
@media (max-width: 580px) {
  .assisted-order {
    padding: 18px 18px 16px;
    border-radius: 22px;
  }
  .assisted-order h2 {
    font-size: 22px;
  }
  .assisted-message pre {
    padding: 52px 14px 14px;
  }
  .assisted-consequence {
    text-align: left;
    margin-bottom: 0;
  }
  .assisted-order .action-row > .primary {
    flex: 1 1 100%;
  }
}
</style>
