<script setup lang="ts">
import { t as tr } from '~/i18n'
import { supplierDisplayName } from '~/utils/glossary'
import { dayOf, endsCaseWith, named, unbroken, type Purchase } from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Goods already bought in this restock that have not all arrived (a supplier that confirmed only
// part, while the rest is found elsewhere): one line each, "百川批发 10 件 · 9/8 到", with a link to
// record the arrival. When recording it would end the restock with its gap still open (everything
// bought is then in), that consequence is said once, at that moment, before anything is sent.
/** `others`: leave out the Case's current purchase, which the stage itself is showing. */
const props = defineProps<{ others?: boolean }>()
const flow = useFlow()
const rows = computed(() =>
  flow.purchases.value.filter(
    (p) => p.accepted > 0 && p.received < p.accepted && !(props.others && p.current),
  ),
)
/** Everything this restock bought, which is what it ends with when recording closes it. */
const bought = computed(() =>
  flow.purchases.value.filter((p) => p.status === 'SUCCEEDED').reduce((n, p) => n + p.accepted, 0),
)
const open = ref<string | null>(null)
const counts = reactive<Record<string, number>>({})
const error = ref('')
const saving = ref(false)
const outstanding = (p: Purchase) => p.accepted - p.received
const counted = (p: Purchase) => counts[p.actionId] ?? outstanding(p)
function start(p: Purchase) {
  error.value = ''
  open.value = p.actionId
}
async function record(p: Purchase) {
  const quantity = counted(p)
  error.value = ''
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > outstanding(p)) {
    error.value = '到货数量要在 1 和未到数量之间。'
    return
  }
  saving.value = true
  try {
    await flow.recordArrival(p.actionId, quantity)
    delete counts[p.actionId]
    open.value = null
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <ul v-if="rows.length" class="rf-purchases" :aria-label="tr('已买到、还没到齐的货')">
    <li v-for="p in rows" :key="p.actionId" class="rf-purchase" :data-purchase="p.actionId">
      <span class="rf-purchase-mark" aria-hidden="true"><AppIcon name="truck" /></span>
      <span class="rf-purchase-what">{{
        unbroken(
          [
            named('{0} {1} 件', [
              p.supplierName || supplierDisplayName(p.supplierId),
              outstanding(p),
            ]),
            p.arrivalAt ? tr('{0} 到', [dayOf(p.arrivalAt)]) : '',
          ]
            .filter(Boolean)
            .join(' · '),
        )
      }}</span>
      <button
        v-if="open !== p.actionId && p.byHand !== false && flow.operator.value"
        type="button"
        class="text-link"
        data-purchase-record
        @click="start(p)"
      >
        {{ tr('登记到货') }}
      </button>
      <div v-if="open === p.actionId" class="rf-purchase-record">
        <p v-if="endsCaseWith(p, counted(p))" class="rf-consequence" role="status">
          {{ tr('登记后，这次应急补货按 {0} 件结束；要补缺口先点「缺的找别家补上」。', [bought]) }}
        </p>
        <label class="rf-count"
          >{{ tr('这次到了')
          }}<input
            type="number"
            min="1"
            :max="outstanding(p)"
            :value="counted(p)"
            :disabled="saving"
            data-purchase-quantity
            @input="counts[p.actionId] = Number(($event.target as HTMLInputElement).value)"
          />{{ tr('件') }}</label
        ><button
          type="button"
          class="secondary"
          :disabled="saving"
          data-purchase-arrival
          @click="record(p)"
        >
          {{ tr(saving ? '正在登记…' : '登记到货') }}</button
        ><button type="button" class="text-link" :disabled="saving" @click="open = null">
          {{ tr('先不登记') }}
        </button>
      </div>
    </li>
    <li v-if="error" class="rf-purchase-error">
      <p class="notice amber" role="alert">{{ tr(error) }}</p>
    </li>
  </ul>
</template>
