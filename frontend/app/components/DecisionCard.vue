<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { money, when } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import { isRecoveryPlan, planOptions, selectedPlanCandidate } from '~/utils/plans'
const { s, plan, product, mission, hasRole } = useShop()
// `held`: the facts moved on and the plan is being re-checked; it stays readable but not actionable.
const props = defineProps<{ held?: boolean }>()
defineEmits<{ confirm: []; evidence: []; compare: [] }>()
const locked = computed(() => Boolean(s.busy) || props.held)
const selected = computed(() => selectedPlanCandidate(plan.value, s.selected))
const recommended = computed(() => plan.value?.proposed_purchase?.quantity || 0)
const options = computed(() => planOptions(plan.value))
const changed = computed(() => s.selected !== recommended.value)
const canConfirm = computed(
  () =>
    hasRole('approver') &&
    (!changed.value || s.selected === 0 || (hasRole('operator') && s.session?.planRevision)),
)
const expanded = ref(false)
onMounted(() => (expanded.value = window.innerWidth > 580))
</script>
<template>
  <article v-if="plan && selected" class="decision-card glass">
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
          joinText([
            tr('剩余需求假设'),
            tr(plan.input_snapshot.forecast.remaining_demand),
            tr('件，在库'),
            tr(plan.input_snapshot.state.stocks.find((x) => x.sku_id === mission?.sku_id)?.on_hand),
            tr('件，周期内可到的在途'),
            tr(plan.input_snapshot.eligible_inbound_qty),
            tr('件。'),
          ])
        }}
      </p>
      <div class="task-context-line">
        <b>{{ product?.name }}</b
        ><span>{{ supplierDisplayName(plan.input_snapshot.offer.supplier_id) }}</span>
      </div>
      <p class="timing-note">
        {{
          joinText([
            tr('预计到货：'),
            tr(when(plan.proposed_purchase?.expected_arrival_at)),
            tr('· 需求周期截至'),
            tr(when(plan.input_snapshot.forecast.horizon_end)),
          ])
        }}
      </p>
      <div class="impact-grid" aria-live="polite">
        <div class="impact">
          <div class="impact-label">{{ tr('采购后预计缺货') }}</div>
          <div class="impact-value blue">
            {{ tr(selected.shortage_qty) }}<small>{{ tr('件') }}</small>
          </div>
          <div class="impact-foot">{{ tr('来自当前方案推演') }}</div>
        </div>
        <div class="impact">
          <div class="impact-label">{{ tr('本次支出') }}</div>
          <div class="impact-value">{{ tr(money(selected.spend_minor)) }}</div>
          <div class="impact-foot">
            {{
              joinText([
                tr(s.selected),
                tr('件 ×'),
                tr(money(plan.input_snapshot.offer.unit_price_minor)),
              ])
            }}
          </div>
        </div>
        <div class="impact">
          <div class="impact-label">{{ tr('采购后现金') }}</div>
          <div class="impact-value">{{ tr(money(selected.cash_after_minor)) }}</div>
          <div class="impact-foot">
            {{ joinText([tr('底线'), tr(money(plan.input_snapshot.policy.cash_floor_minor))]) }}
          </div>
        </div>
      </div>
      <p class="assumption-note">
        {{ tr('按当前需求、按时到货估算；不是销量或资金安全的保证。')
        }}<button class="text-link" @click="$emit('evidence')">{{ tr('查看依据') }}</button>
      </p>
      <div class="option-title">
        <span>{{ tr('选择这次的安排') }}</span
        ><button class="text-link" @click="$emit('compare')">
          {{ tr('比较全部候选') }}<AppIcon name="chevron-right" />
        </button>
      </div>
      <p v-if="isRecoveryPlan(plan)" class="source-note">
        {{ tr('这份待确认方案对应已采纳的报价。更换供应商或数量，请回到供应异常应对重新分析。') }}
      </p>
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
            :disabled="locked"
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
              joinText([
                tr('现金'),
                tr(money(c.cash_after_minor)),
                tr('· 预计缺'),
                tr(c.shortage_qty),
                tr('件'),
              ])
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
        ><button class="primary" :disabled="locked || !canConfirm" @click="$emit('confirm')">
          {{ tr(s.selected ? `核对 ${s.selected} 件采购` : '记录本轮取舍')
          }}<AppIcon name="arrow-right" />
        </button>
      </div>
    </div>
  </article>
</template>
