<script setup lang="ts">
import { when, actionLabel } from '~/utils/presentation'
const { s, mission, product, stock, unresolved, canDecide, hasRole } = useShop()
defineProps<{ conversation?: boolean }>()
defineEmits<{ pause: []; resume: []; receipt: []; mission: []; check: [] }>()
const waiting = computed(() =>
  unresolved.value
    ? `原采购：${actionLabel(unresolved.value.status)}`
    : mission.value?.status === 'PAUSED'
      ? '你恢复主动跟进；已有订单仍更新事实'
      : canDecide.value
        ? '你确认本次安排'
        : stock.value?.in_transit
          ? `${stock.value.in_transit} 件采购到货`
          : s.plan?.status === 'REJECTED'
            ? '出现新事实后再评估，当前取舍保持'
            : '下一次经营变化，活动未自动结束',
)
</script>
<template>
  <article v-if="mission" class="follow-panel glass">
    <div class="follow-panel-head">
      <div>
        <span class="tag" :class="mission.status === 'ACTIVE' ? 'green' : 'gray'"
          ><AppIcon :name="mission.status === 'ACTIVE' ? 'orbit' : 'pause'" />{{
            mission.status === 'ACTIVE'
              ? '备货委托进行中'
              : mission.status === 'PAUSED'
                ? '主动跟进已暂停'
                : '委托已结束'
          }}</span
        >
        <h3>{{ product?.name }}</h3>
      </div>
      <button
        v-if="['ACTIVE', 'PAUSED'].includes(mission.status)"
        class="text-link"
        :disabled="Boolean(s.busy) || !hasRole('operator')"
        @click="mission.status === 'PAUSED' ? $emit('resume') : $emit('pause')"
      >
        {{ mission.status === 'PAUSED' ? '恢复跟进' : '暂停跟进' }}
      </button>
    </div>
    <dl class="follow-facts">
      <div>
        <dt>正在等</dt>
        <dd>{{ waiting }}</dd>
      </div>
      <div>
        <dt>最近检查</dt>
        <dd>{{ when(s.dashboard?.last_check_at) }}</dd>
      </div>
      <div>
        <dt>下一次检查</dt>
        <dd>
          {{ mission.status === 'ACTIVE' ? when(mission.schedule.next_run_at) : '已暂停或结束' }}
        </dd>
      </div>
      <div v-if="s.inbounds.some((i) => i.remaining_quantity)">
        <dt>预计到货</dt>
        <dd v-for="i in s.inbounds.filter((i) => i.remaining_quantity)" :key="i.action_id">
          {{ i.remaining_quantity }} 件 · {{ when(i.expected_arrival_at)
          }}<span v-if="i.is_overdue"> · 已超过预计时间</span>
        </dd>
      </div>
    </dl>
    <p v-if="s.plan?.status === 'REJECTED'" class="notice amber">
      本轮不采购已记录。条件不变时不反复催促；后台会继续核对经营变化。
    </p>
    <p class="channel-note">
      {{
        mission.status === 'PAUSED'
          ? '主动检查已暂停；已提交的动作仍需核实。'
          : !s.connected
            ? '当前连接不可用，无法确认新的检查结果。'
            : '最近检查记录与已登记的下次计划如上。'
      }}
      进展保存在应用内，不发送外部通知。
    </p>
    <div class="follow-links">
      <button v-if="s.actions.length" class="text-link" @click="$emit('receipt')">
        查看采购与到货记录</button
      ><button class="text-link" @click="$emit('mission')">查看委托</button
      ><button
        class="text-link"
        :disabled="Boolean(s.busy) || mission.status !== 'ACTIVE' || !hasRole('operator')"
        @click="$emit('check')"
      >
        重新检查
      </button>
    </div>
  </article>
</template>
