<script setup lang="ts">
import { t as tr } from '~/i18n'
import { money, when } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'

// The plan awaiting the owner's decision. Same data and behaviour as DecisionCard (selection in
// shop state, recommendation marked separately, confirmation through the page's review step);
// only the wording and spacing follow the workspace vocabulary.
const { s, plan, product, mission, hasRole } = useShop()
const emit = defineEmits<{ confirm: []; open: [name: string] }>()
const selected = computed(() => plan.value?.candidates.find((c) => c.quantity === s.selected))
const recommended = computed(() => plan.value?.proposed_purchase?.quantity || 0)
const options = computed(() => {
  const order = [...new Set([recommended.value, 20, 40, 0])]
  return (plan.value?.candidates || [])
    .filter(
      (c) =>
        order.includes(c.quantity) && c.rejection_reasons.every((r) => r === 'TASK_QUANTITY_LIMIT'),
    )
    .sort((a, b) => order.indexOf(a.quantity) - order.indexOf(b.quantity))
})
const changed = computed(() => s.selected !== recommended.value)
const canConfirm = computed(
  () =>
    hasRole('approver') &&
    (!changed.value || s.selected === 0 || (hasRole('operator') && s.session?.planRevision)),
)
const onHand = computed(
  () =>
    plan.value?.input_snapshot.state.stocks.find((x) => x.sku_id === mission.value?.sku_id)
      ?.on_hand,
)
// Small screens start with the candidates folded, like the decision card.
const expanded = ref(false)
onMounted(() => (expanded.value = window.innerWidth > 580))
</script>
<template>
  <article v-if="plan && selected" class="decision-card glass space-plan-card">
    <div class="card-core">
      <h2>
        {{
          changed
            ? tr('你正在查看：{0}', [
                s.selected ? tr('补 {0} 件', [s.selected]) : tr('本轮暂不补货'),
              ])
            : tr('建议补货 {0} 件', [recommended])
        }}
      </h2>
      <p class="decision-lead">
        {{
          tr('剩余需求假设 {0} 件，在库 {1} 件，周期内可到的在途 {2} 件。', [
            plan.input_snapshot.forecast.remaining_demand,
            onHand ?? tr('未取得'),
            plan.input_snapshot.eligible_inbound_qty,
          ])
        }}
      </p>
      <div class="task-context-line">
        <b>{{ product?.name }}</b
        ><span>{{ supplierDisplayName(plan.input_snapshot.offer.supplier_id) }}</span>
        <button class="text-link" @click="emit('open', 'mission')">
          {{ tr('查看这项委托') }}<AppIcon name="chevron-right" />
        </button>
      </div>
      <p class="timing-note">
        {{
          tr('预计到货 {0} · 需求周期截至 {1}', [
            when(plan.proposed_purchase?.expected_arrival_at),
            when(plan.input_snapshot.forecast.horizon_end),
          ])
        }}
      </p>
      <p v-if="changed" class="selection-note">
        {{
          tr('系统当前推荐 {0} 件；下面的影响与确认对象对应你选择的 {1} 件。', [
            recommended,
            s.selected,
          ])
        }}
      </p>
      <div class="impact-grid" aria-live="polite">
        <div class="impact">
          <div class="impact-label">{{ tr('采购后预计缺货') }}</div>
          <div class="impact-value blue">
            {{ tr(selected.shortage_qty) }}<small>{{ ' ' + tr('件') }}</small>
          </div>
          <div class="impact-foot">{{ tr('来自当前方案推演') }}</div>
        </div>
        <div class="impact">
          <div class="impact-label">{{ tr('本次支出') }}</div>
          <div class="impact-value">{{ tr(money(selected.spend_minor)) }}</div>
          <div class="impact-foot">
            {{
              tr('{0} 件 × {1}', [s.selected, money(plan.input_snapshot.offer.unit_price_minor)])
            }}
          </div>
        </div>
        <div class="impact">
          <div class="impact-label">{{ tr('采购后现金') }}</div>
          <div class="impact-value">{{ tr(money(selected.cash_after_minor)) }}</div>
          <div class="impact-foot">
            {{ tr('底线 {0}', [money(plan.input_snapshot.policy.cash_floor_minor)]) }}
          </div>
        </div>
      </div>
      <p class="assumption-note">
        {{ tr('按当前需求、按时到货估算；不是销量或资金安全的保证。')
        }}<button class="text-link" @click="emit('open', 'evidence')">{{ tr('查看依据') }}</button>
      </p>
      <div class="option-title">
        <span>{{ tr('选择这次的安排') }}</span
        ><button class="text-link" @click="emit('open', 'compare')">
          {{ tr('比较全部候选') }}<AppIcon name="chevron-right" />
        </button>
      </div>
      <details
        class="options-disclosure"
        :open="expanded || changed"
        @toggle="expanded = ($event.target as HTMLDetailsElement).open"
      >
        <summary>{{ tr('更改安排，也可以本轮暂不补货') }}</summary>
        <div class="options" role="group" :aria-label="tr('采购选项')">
          <button
            v-for="c in options"
            :key="c.id"
            class="option"
            :class="{ selected: s.selected === c.quantity }"
            :aria-pressed="s.selected === c.quantity"
            :disabled="Boolean(s.busy)"
            @click="s.selected = c.quantity"
          >
            <span class="option-top"
              ><span class="radio-dot" /><strong>{{
                c.quantity ? tr('补 {0} 件', [c.quantity]) : tr('本轮暂不补货')
              }}</strong
              ><span v-if="c.quantity === recommended" class="recommended">{{
                tr('推荐')
              }}</span></span
            ><small>{{
              tr('现金 {0} · 预计缺 {1} 件', [money(c.cash_after_minor), c.shortage_qty])
            }}</small>
          </button>
        </div>
      </details>
      <p v-if="changed && s.selected !== 0 && !s.session?.planRevision" class="notice amber">
        {{ tr('此后端暂不支持确认其他数量；可以比较，或确认当前推荐。') }}
      </p>
      <p v-if="!hasRole('approver')" class="channel-note">
        {{ tr('当前身份可查看方案，采购确认需要审批权限。') }}
      </p>
      <p v-else-if="changed && s.selected !== 0 && !hasRole('operator')" class="channel-note">
        {{ tr('调整采购数量还需要方案修订权限，请由有权限的用户先准备新方案。') }}
      </p>
      <div class="action-row">
        <span class="action-note"
          ><AppIcon name="lock-keyhole" />{{ tr('下一步核对，尚未采购') }}</span
        ><button
          class="primary"
          :disabled="Boolean(s.busy) || !canConfirm"
          @click="emit('confirm')"
        >
          {{ s.selected ? tr('核对 {0} 件采购', [s.selected]) : tr('记录本轮取舍')
          }}<AppIcon name="arrow-right" />
        </button>
      </div>
    </div>
  </article>
</template>
