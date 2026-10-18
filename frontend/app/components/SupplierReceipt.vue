<script setup lang="ts">
// What was read from the reply the owner pasted, each value beside the words it came from.
import { joinText, t as tr } from '~/i18n'
import { money } from '~/utils/presentation'
import type { Schema } from '~/types/models'
const props = defineProps<{ reply: Schema<'SupplierReply'> }>()
const outcomes: Record<string, string> = {
  confirmed: '供应商已确认',
  declined: '供应商未接单',
  partial: '只确认了一部分',
  needs_attention: '还不能确认',
}
const names: Record<string, string> = {
  quantity: '数量',
  unit_price_minor: '单价',
  total_minor: '合计',
}
const shown = (field: string, value: number) =>
  field === 'quantity' ? joinText([tr(value), tr('件')]) : tr(money(value))
const amount = (field: string, value: number | null) => (value == null ? '' : shown(field, value))
const rows = computed(() =>
  [
    { field: 'quantity', label: '确认数量', value: amount('quantity', props.reply.quantity) },
    {
      field: 'unit_price_minor',
      label: '确认单价',
      value: amount('unit_price_minor', props.reply.unit_price_minor),
    },
    {
      field: 'total_minor',
      label: '确认金额',
      value: amount('total_minor', props.reply.total_minor),
    },
    { field: 'delivery_date', label: '确认交期', value: props.reply.delivery_date || '' },
    {
      field: 'supplier_order_ref',
      label: '供应商单号',
      value: props.reply.supplier_order_ref || '',
    },
  ].filter((row) => row.value),
)
</script>
<template>
  <section class="supplier-receipt" :data-outcome="reply.outcome">
    <h4>
      {{ joinText([tr('回执 ·'), tr(outcomes[reply.outcome] || reply.outcome)]) }}
    </h4>
    <p v-if="reply.outcome === 'needs_attention' && !reply.differences.length" class="notice amber">
      {{ tr('这条回复里没有读到明确的接受或拒绝，订单保持待确认。') }}
    </p>
    <ul v-if="reply.differences.length" class="notice amber">
      <li v-for="difference in reply.differences" :key="difference.field">
        {{
          joinText([
            tr(names[difference.field] || difference.field),
            tr('与订单不一致：订单'),
            shown(difference.field, difference.ordered),
            tr('，回复'),
            shown(difference.field, difference.replied),
          ])
        }}
      </li>
    </ul>
    <div v-for="row in rows" :key="row.field" class="detail-row">
      <span>{{ tr(row.label) }}</span
      ><b
        >{{ row.value
        }}<small v-if="reply.quotes[row.field]">{{
          joinText([tr('原话：'), reply.quotes[row.field]])
        }}</small></b
      >
    </div>
    <details>
      <summary>{{ tr('供应商回复原文') }}</summary>
      <pre>{{ reply.text }}</pre>
      <small>{{
        tr(reply.read_by === 'model' ? '由模型读取，每项都核对过原话。' : '按固定规则读取。')
      }}</small>
    </details>
  </section>
</template>
<style scoped>
.supplier-receipt {
  border: 1px solid #dce6dd;
  border-radius: 14px;
  padding: 14px 16px;
  margin: 12px 0;
  background: #ffffffa8;
}
.supplier-receipt[data-outcome='needs_attention'],
.supplier-receipt[data-outcome='partial'] {
  border-color: #e3c98b;
}
.supplier-receipt h4 {
  margin: 0 0 10px;
}
.supplier-receipt small {
  display: block;
  color: #607468;
  font-weight: 400;
  overflow-wrap: anywhere;
}
.supplier-receipt pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 0.85rem;
  margin: 8px 0;
}
.supplier-receipt ul {
  padding-left: 28px;
}
</style>
