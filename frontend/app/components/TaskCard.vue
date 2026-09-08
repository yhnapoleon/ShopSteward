<script setup lang="ts">
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
        ><AppIcon name="layers-2" />活动备货 · {{ mission.id.slice(-8) }}</span
      ><span class="tag" :class="status.tone">{{ status.label }}</span>
    </div>
    <h2>
      {{
        canDecide && plan?.proposed_purchase
          ? `建议补货 ${plan.proposed_purchase.quantity} 件`
          : mission.objective
      }}
    </h2>
    <p class="task-card-context">{{ product?.name }}<span>·</span>{{ status.detail }}</p>
    <div v-if="canDecide && plan?.proposed_purchase" class="task-card-impact">
      <div>
        <span>本次支出</span><b>{{ money(plan.proposed_purchase.total_minor) }}</b>
      </div>
      <div>
        <span>采购后预计现金</span
        ><b>{{
          money(
            plan.candidates.find((c) => c.quantity === plan?.proposed_purchase?.quantity)
              ?.cash_after_minor,
          )
        }}</b>
      </div>
      <div>
        <span>预计到货</span
        ><b class="task-time">{{ when(plan.proposed_purchase.expected_arrival_at) }}</b>
      </div>
    </div>
    <div class="task-card-bottom">
      <div class="task-card-progress">
        <span class="agent-live-dot" :class="{ 'is-running': agent.running.value }" /><span>{{
          agent.active.value || agent.s.syncError
            ? agent.status.value
            : '决定、执行与对话保留在同一任务'
        }}</span>
      </div>
      <button class="primary" @click="$emit('open')">
        {{
          status.group === '已完成' || status.group === '已结束'
            ? '查看任务记录'
            : '查看任务与方案'
        }}<AppIcon name="arrow-up-right" />
      </button>
    </div>
  </motion.article>
</template>
