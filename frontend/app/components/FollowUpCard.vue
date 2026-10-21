<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { when, actionLabel } from '~/utils/presentation'
const { s, mission, product, stock, unresolved, canDecide, hasRole } = useShop()
defineProps<{ conversation?: boolean }>()
defineEmits<{ pause: []; resume: []; receipt: []; mission: []; check: [] }>()
const waiting = computed(() =>
  unresolved.value
    ? tr('原采购：{0}', [tr(actionLabel(unresolved.value.status, unresolved.value.channel))])
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
const checks = computed(() =>
  joinText(
    [
      tr('最近检查：{0}', [when(s.dashboard?.last_check_at)]),
      '·',
      mission.value?.status === 'ACTIVE'
        ? tr('下一检查：{0}', [when(mission.value.schedule.next_run_at)])
        : tr('已暂停或结束'),
    ],
    ' ',
  ),
)
</script>
<template>
  <article v-if="mission" class="follow-panel glass">
    <div class="follow-panel-head">
      <div>
        <span class="tag" :class="mission.status === 'ACTIVE' ? 'green' : 'gray'"
          ><AppIcon :name="mission.status === 'ACTIVE' ? 'orbit' : 'pause'" />{{
            tr(
              mission.status === 'ACTIVE'
                ? '备货委托进行中'
                : mission.status === 'PAUSED'
                  ? '主动跟进已暂停'
                  : '委托已结束',
            )
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
        {{ tr(mission.status === 'PAUSED' ? '恢复跟进' : '暂停跟进') }}
      </button>
    </div>
    <!-- Checks run on the real-world clock, not the business time the page shows: when the last
         one ran and the next one is due stay behind the facts (hover). -->
    <dl class="follow-facts" :title="checks">
      <div>
        <dt>{{ tr('正在等') }}</dt>
        <dd>{{ tr(waiting) }}</dd>
      </div>
      <div v-if="s.inbounds.some((i) => i.remaining_quantity)">
        <dt>{{ tr('预计到货') }}</dt>
        <dd v-for="i in s.inbounds.filter((i) => i.remaining_quantity)" :key="i.action_id">
          {{ joinText([tr(i.remaining_quantity), tr('件 ·'), tr(when(i.expected_arrival_at))])
          }}<span v-if="i.is_overdue">{{ tr('· 已超过预计时间') }}</span>
        </dd>
      </div>
    </dl>
    <p v-if="s.plan?.status === 'REJECTED'" class="notice amber">
      {{ tr('本轮不采购已记录。条件不变时不反复催促；后台会继续核对经营变化。') }}
    </p>
    <!-- Only something out of the ordinary is said; the records above speak for themselves. -->
    <p v-if="mission.status === 'PAUSED' || !s.connected" class="channel-note">
      {{
        tr(
          mission.status === 'PAUSED'
            ? '主动检查已暂停；已提交的动作仍需核实。'
            : '当前连接不可用，无法确认新的检查结果。',
        )
      }}
    </p>
    <div class="follow-links">
      <button v-if="s.actions.length" class="text-link" @click="$emit('receipt')">
        {{ tr('查看采购与到货记录') }}</button
      ><button class="text-link" @click="$emit('mission')">{{ tr('查看委托') }}</button
      ><button
        class="text-link"
        :disabled="Boolean(s.busy) || mission.status !== 'ACTIVE' || !hasRole('operator')"
        @click="$emit('check')"
      >
        {{ tr('重新检查') }}
      </button>
    </div>
  </article>
</template>
