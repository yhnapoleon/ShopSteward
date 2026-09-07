<script setup lang="ts">
import { money, when } from '~/utils/presentation'
const { s, plan, product, mission, hasRole } = useShop()
defineEmits<{ confirm: []; evidence: []; compare: []; mission: [] }>()
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
const expanded = ref(false)
onMounted(() => (expanded.value = window.innerWidth > 580))
</script>
<template>
  <article v-if="plan && selected" class="decision-card glass">
    <div class="card-core">
      <div class="card-meta">
        <span class="tag"><AppIcon name="flag" />待你决定</span
        ><button class="text-link" @click="$emit('mission')">
          同一项备货委托<AppIcon name="chevron-right" />
        </button>
      </div>
      <div class="task-context-line">
        <b>{{ product?.name }}</b
        ><span>活动备货 · {{ plan.input_snapshot.offer.supplier_id }}</span>
      </div>
      <p class="timing-note">
        预计到货：{{ when(plan.proposed_purchase?.expected_arrival_at) }} · 需求周期截至
        {{ when(plan.input_snapshot.forecast.horizon_end) }}
      </p>
      <h2>
        {{
          changed
            ? `你正在查看：${s.selected ? `补 ${s.selected} 件` : '本轮暂不补货'}`
            : `建议补货 ${recommended} 件`
        }}
      </h2>
      <p class="decision-lead">
        剩余需求假设 {{ plan.input_snapshot.forecast.remaining_demand }} 件，在库
        {{ plan.input_snapshot.state.stocks.find((x) => x.sku_id === mission?.sku_id)?.on_hand }}
        件，周期内可到的在途 {{ plan.input_snapshot.eligible_inbound_qty }} 件。
      </p>
      <p v-if="changed" class="selection-note">
        系统当前推荐 {{ recommended }} 件；下面影响与确认对象对应你选择的
        <b>{{ s.selected }} 件</b>。
      </p>
      <div class="impact-grid" aria-live="polite">
        <div class="impact">
          <div class="impact-label">采购后预计缺货</div>
          <div class="impact-value blue">{{ selected.shortage_qty }}<small>件</small></div>
          <div class="impact-foot">来自当前方案推演</div>
        </div>
        <div class="impact">
          <div class="impact-label">本次支出</div>
          <div class="impact-value">{{ money(selected.spend_minor) }}</div>
          <div class="impact-foot">
            {{ s.selected }} 件 × {{ money(plan.input_snapshot.offer.unit_price_minor) }}
          </div>
        </div>
        <div class="impact">
          <div class="impact-label">采购后现金</div>
          <div class="impact-value">{{ money(selected.cash_after_minor) }}</div>
          <div class="impact-foot">
            底线 {{ money(plan.input_snapshot.policy.cash_floor_minor) }}
          </div>
        </div>
      </div>
      <p class="assumption-note">
        按当前需求、按时到货估算；不是销量或资金安全的保证。<button
          class="text-link"
          @click="$emit('evidence')"
        >
          查看依据
        </button>
      </p>
      <div class="option-title">
        <span>选择这次的安排</span
        ><button class="text-link" @click="$emit('compare')">
          比较全部候选<AppIcon name="chevron-right" />
        </button>
      </div>
      <details
        class="options-disclosure"
        :open="expanded || changed"
        @toggle="expanded = ($event.target as HTMLDetailsElement).open"
      >
        <summary>更改安排，也可以本轮暂不补货</summary>
        <div class="options" role="group" aria-label="采购选项">
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
                c.quantity ? `补 ${c.quantity} 件` : '本轮暂不补货'
              }}</strong
              ><span v-if="c.quantity === recommended" class="recommended">推荐</span></span
            ><small>现金 {{ money(c.cash_after_minor) }} · 预计缺 {{ c.shortage_qty }} 件</small>
          </button>
        </div>
      </details>
      <p v-if="changed && s.selected !== 0 && !s.session?.planRevision" class="notice amber">
        此后端暂不支持确认其他数量；可以比较，或确认当前推荐。
      </p>
      <p v-if="!hasRole('approver')" class="channel-note">
        当前身份可查看方案，采购确认需要审批权限。
      </p>
      <p v-else-if="changed && s.selected !== 0 && !hasRole('operator')" class="channel-note">
        调整采购数量还需要方案修订权限，请由有权限的用户先准备新方案。
      </p>
      <div class="action-row">
        <span class="action-note"><AppIcon name="lock-keyhole" />下一步核对，尚未采购</span
        ><button
          class="primary"
          :disabled="Boolean(s.busy) || !canConfirm"
          @click="$emit('confirm')"
        >
          {{ s.selected ? `核对 ${s.selected} 件采购` : '记录本轮取舍'
          }}<AppIcon name="arrow-right" />
        </button>
      </div>
    </div>
    <AgentConversation />
  </article>
</template>
