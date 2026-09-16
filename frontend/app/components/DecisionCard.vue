<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
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
      <h2>
        {{
          tr(
            changed
              ? `你正在查看：${s.selected ? `补 ${s.selected} 件` : '本轮暂不补货'}`
              : `建议补货 ${recommended} 件`,
          )
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
        ><span>{{ joinText([tr('活动备货 ·'), plan.input_snapshot.offer.supplier_id]) }}</span>
        <button class="text-link" @click="$emit('mission')">
          {{ tr('查看这项委托') }}<AppIcon name="chevron-right" />
        </button>
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
      <p v-if="changed" class="selection-note">
        {{
          joinText([tr('系统当前推荐'), tr(recommended), tr('件；下面影响与确认对象对应你选择的')])
        }}<b>{{ joinText([tr(s.selected), tr('件')]) }}</b
        >。
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
                tr(c.quantity ? `补 ${c.quantity} 件` : '本轮暂不补货')
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
        ><button
          class="primary"
          :disabled="Boolean(s.busy) || !canConfirm"
          @click="$emit('confirm')"
        >
          {{ tr(s.selected ? `核对 ${s.selected} 件采购` : '记录本轮取舍')
          }}<AppIcon name="arrow-right" />
        </button>
      </div>
    </div>
  </article>
</template>
