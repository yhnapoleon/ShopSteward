<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { motion, useReducedMotion } from 'motion-v'
import { money, when } from '~/utils/presentation'
const { s, mission, plan, product, canDecide } = useShop()
const { status } = useTaskPresentation()
const agent = useAgentConversation()
const reduce = useReducedMotion()
defineEmits<{ open: [] }>()
</script>
<template>
  <motion.article
    v-if="mission"
    class="task-card glass"
    :data-task-id="mission.id"
    :layout="!reduce"
    :transition="{ duration: reduce ? 0 : 0.24 }"
  >
    <div class="task-card-top">
      <span class="task-identity"
        ><AppIcon name="layers-2" />{{
          joinText([tr('活动备货 ·'), tr(mission.id.slice(-8))])
        }}</span
      ><span class="tag" :class="status.tone">{{ tr(status.label) }}</span>
    </div>
    <h2>
      {{
        canDecide && plan?.proposed_purchase
          ? tr('建议补货 {0} 件', [plan.proposed_purchase.quantity])
          : mission.objective
      }}
    </h2>
    <p class="task-card-context">{{ product?.name }}<span>·</span>{{ tr(status.detail) }}</p>
    <div v-if="canDecide && plan?.proposed_purchase" class="task-card-impact">
      <div>
        <span>{{ tr('本次支出') }}</span
        ><b>{{ tr(money(plan.proposed_purchase.total_minor)) }}</b>
      </div>
      <div>
        <span>{{ tr('采购后预计现金') }}</span
        ><b>{{
          tr(
            money(
              plan.candidates.find((c) => c.quantity === plan?.proposed_purchase?.quantity)
                ?.cash_after_minor,
            ),
          )
        }}</b>
      </div>
      <div>
        <span>{{ tr('预计到货') }}</span
        ><b class="task-time">{{ tr(when(plan.proposed_purchase.expected_arrival_at)) }}</b>
      </div>
    </div>
    <div class="task-card-bottom">
      <div class="task-card-progress">
        <span class="agent-live-dot" :class="{ 'is-running': agent.running.value }" /><span>{{
          tr(
            agent.active.value || agent.s.syncError
              ? agent.status.value
              : '决定、执行与对话保留在同一任务',
          )
        }}</span>
      </div>
      <button class="primary" @click="$emit('open')">
        {{
          tr(
            status.group === '已完成' || status.group === '已结束'
              ? '查看任务记录'
              : '查看任务与方案',
          )
        }}<AppIcon name="arrow-up-right" />
      </button>
    </div>
  </motion.article>
</template>
