<script setup lang="ts">
import { t as tr } from '~/i18n'
import { orderStatus, supplierDisplayName } from '~/utils/glossary'
import { money, when } from '~/utils/presentation'

// Purchase orders of this mission, newest first: what was bought, where it stands, and how much
// has actually arrived. Identifiers stay inside each row's disclosure. The status words are
// shared with the business brief (utils/glossary.ts).
const emit = defineEmits<{ open: [name: string] }>()
const { s } = useShop()
const space = useSpace()
const { actions } = space
const orders = computed(() =>
  [...actions.value]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .map((action) => {
      const inbound = s.inbounds.find((i) => i.action_id === action.id)
      const ordered = inbound?.ordered_quantity || action.quantity
      const received = inbound?.received_quantity || 0
      return {
        action,
        inbound,
        ordered,
        received,
        ratio: ordered ? Math.min(1, received / ordered) : 0,
        status: orderStatus(action, inbound),
        arrival: inbound?.expected_arrival_at || action.purchase_snapshot.expected_arrival_at,
        // A failed or cancelled order brings nothing; arrival is only tracked for live ones.
        tracked: ['QUEUED', 'EXECUTING', 'SUCCEEDED', 'UNKNOWN'].includes(action.status),
      }
    }),
)
// The newest order failed or was declined and no emergency restock is under way: offer one (§18).
const shop = useShop()
const launcher = useRecoveryLaunch()
const restockable = computed(() => {
  const newest = orders.value[0]?.action
  const mission = space.mission.value
  return newest?.status === 'FAILED' &&
    !!mission &&
    mission.status === 'ACTIVE' &&
    !!s.session?.recoveryCases &&
    shop.hasRole('operator') &&
    !launcher.inProgress(mission.id)
    ? newest
    : null
})
function restock() {
  const failed = restockable.value
  if (!failed) return
  const declined = failed.supplier_reply?.outcome === 'declined'
  launcher.request({
    missionId: failed.mission_id,
    reason: declined ? 'declined' : 'failed',
    exclude: declined ? failed.purchase_snapshot.supplier_id : null,
  })
}
// New orders slide in once; the list does not replay when the page refreshes in the background.
const live = ref(false)
onMounted(() => nextTick(() => (live.value = true)))
</script>
<template>
  <section
    v-if="orders.length"
    id="space-receipt"
    class="space-orders glass space-target"
    :class="{ 'target-active': space.isTarget('receipt') }"
    :aria-label="tr('采购与到货')"
  >
    <div class="task-section-heading">
      <h2>{{ tr('采购与到货') }}</h2>
      <button class="text-link" @click="emit('open', 'receipt')">
        {{ tr('查看采购与到货记录') }}<AppIcon name="arrow-up-right" />
      </button>
    </div>
    <TransitionGroup tag="ul" class="space-order-list" :name="live ? 'space-rise' : 'space-still'">
      <li v-for="o in orders" :key="o.action.id">
        <details class="space-order">
          <summary>
            <span class="space-order-main"
              ><b>{{
                `${tr('{0} 件', [o.action.quantity])} · ${tr(money(o.action.amount_minor))}`
              }}</b
              ><span class="space-order-supplier">{{
                supplierDisplayName(o.action.purchase_snapshot.supplier_id)
              }}</span
              ><span class="tag" :class="o.status.tone">{{ tr(o.status.label) }}</span></span
            ><span v-if="o.tracked" class="space-order-meta">{{
              o.status.label === '已到货'
                ? tr('{0} 件已全部到货', [o.ordered])
                : o.arrival
                  ? tr(o.inbound?.is_overdue ? '预计到货 {0} · 已超过预计时间' : '预计到货 {0}', [
                      when(o.arrival),
                    ])
                  : tr('到货时间待供应商确认')
            }}</span
            ><span v-if="o.tracked" class="space-order-progress"
              ><span class="space-order-bar" aria-hidden="true"
                ><span :style="{ transform: `scaleX(${o.ratio})` }" /></span
              ><small>{{ tr('{0}/{1} 件已到货', [o.received, o.ordered]) }}</small></span
            ><AppIcon name="chevron-down" />
          </summary>
          <dl class="space-order-detail">
            <div>
              <dt>{{ tr('采购编号') }}</dt>
              <dd>{{ tr(o.action.external_order_id || o.action.id) }}</dd>
            </div>
            <div>
              <dt>{{ tr('提交时间') }}</dt>
              <dd>{{ tr(when(o.action.created_at)) }}</dd>
            </div>
            <div>
              <dt>{{ tr('供应商回执') }}</dt>
              <dd>
                {{
                  o.action.receipt
                    ? tr('{0} · {1}', [
                        tr(
                          { ACCEPTED: '已受理', REJECTED: '已拒绝', PENDING: '尚未答复' }[
                            o.action.receipt.status
                          ],
                        ),
                        when(o.action.receipt.recorded_at),
                      ])
                    : tr('尚未取得')
                }}
              </dd>
            </div>
            <div v-if="o.action.last_error">
              <dt>{{ tr('原因') }}</dt>
              <dd>{{ tr(o.action.last_error) }}</dd>
            </div>
          </dl>
        </details>
        <button
          v-if="restockable?.id === o.action.id"
          type="button"
          class="text-link space-order-restock"
          data-recovery-from-order
          @click="restock"
        >
          {{ tr('找别家补') }}<AppIcon name="arrow-right" />
        </button>
      </li>
    </TransitionGroup>
  </section>
</template>
