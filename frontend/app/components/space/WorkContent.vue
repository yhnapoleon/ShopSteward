<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { VIEW_TARGETS, type NextStepTarget } from '~/surfaces/types'
import { money, when } from '~/utils/presentation'

// What the owner and the assistant produced for this item: questions, results, quotations and
// the conditions for starting a restocking mission. A mission item shows only what adds to the
// mission cards above; a standalone item shows its full progress.
const emit = defineEmits<{
  open: [name: string]
  navigate: [view: string]
  changed: []
  converse: []
}>()
const work = useWorkItems()
const { s } = work
const shop = useShop()
const { item, linked } = useSpace()
const simulationStale = computed(() => {
  const c = item.value?.result?.calculation
  return (
    !!c &&
    (c.input.state.state_version !== shop.s.dashboard?.state.state_version ||
      Date.parse(c.valid_until) <= Date.now() ||
      shop.s.dashboard?.freshness.status !== 'FRESH')
  )
})
const expired = computed(
  () =>
    !!item.value?.processing_expires_at &&
    Date.parse(item.value.processing_expires_at) <= Date.now(),
)
const asking = computed(() => item.value?.status === 'WAITING_INPUT' && !!item.value.question)
const stale = computed(() =>
  ['RECEIVED', 'PROCESSING', 'WAITING_INPUT'].includes(item.value?.status || ''),
)
async function accept() {
  if (await work.acceptMission()) emit('changed')
}
// A result surface's next step opens an existing view or dialog; its quick answer is sent through
// the item's conversation like a typed reply, keeping any unsent draft there.
function surfaceOpen(name: NextStepTarget) {
  if (VIEW_TARGETS.includes(name)) emit('navigate', name)
  else emit('open', name)
}
async function surfaceAnswer(text: string) {
  if (s.busy || s.pending) return
  const draft = s.input
  s.input = text
  const sent = await work.send()
  if (sent) {
    s.input = draft
    emit('changed')
  } else if (!s.pending) s.input = draft
}
</script>
<template>
  <template v-if="item">
    <QuotationWorkspace @changed="emit('changed')" />
    <SpaceClarificationCard
      v-if="asking"
      :question="item.question!"
      @changed="emit('changed')"
      @converse="emit('converse')"
    />
    <section
      v-else-if="
        linked
          ? ['RECEIVED', 'PROCESSING', 'BLOCKED'].includes(item.status) || expired
          : !item.result?.calculation || item.status !== 'RESULT_READY'
      "
      class="glass work-status-panel"
    >
      <h2>
        {{
          tr(
            item.status === 'WAITING_INPUT'
              ? '还需要你补充'
              : item.status === 'RECEIVED'
                ? '这件事已经收到'
                : '当前进展',
          )
        }}
      </h2>
      <p>{{ item.question || item.summary || tr('原始要求已保存，可以在右侧继续补充。') }}</p>
      <p>{{ item.result?.calculation ? tr(item.next_step) : item.next_step }}</p>
      <small>{{ joinText([tr('最近更新：'), tr(when(item.updated_at))]) }}</small>
      <p v-if="expired" class="notice amber">
        {{ tr('本轮处理未按时返回，可以重试；已保存的内容仍保留。') }}
      </p>
    </section>
    <template v-if="item.result && item.result.kind !== 'quotation'">
      <details v-if="linked" class="glass space-discussion">
        <summary>{{ tr('这次讨论的结果') }}</summary>
        <p v-if="stale" class="notice">{{ tr('这是之前的结果，尚未根据新要求更新。') }}</p>
        <WorkResult
          :result="item.result"
          :demonstration="item.demonstration"
          interactive
          @open="surfaceOpen"
          @submit="surfaceAnswer"
        />
      </details>
      <section
        v-else
        class="glass work-status-panel"
        :data-onboarding="item.result.calculation ? 'result' : undefined"
      >
        <p v-if="stale" class="notice">{{ tr('这是之前的结果，尚未根据新要求更新。') }}</p>
        <WorkResult
          :result="item.result"
          :demonstration="item.demonstration"
          interactive
          animate
          @open="surfaceOpen"
          @submit="surfaceAnswer"
        />
        <button
          v-if="item.result.calculation"
          class="secondary"
          @click="emit('open', 'simulation')"
        >
          {{ tr('调整条件再试算') }}
        </button>
      </section>
    </template>
    <section v-if="item.mission_request && !linked" class="glass work-status-panel space-request">
      <h2>{{ tr('开始持续跟进这项备货') }}</h2>
      <p>{{ item.mission_request.objective }}</p>
      <p v-if="item.result?.calculation" class="source-note">
        {{ tr('按这里的现金底线和候选数量建立委托，业务系统会用最新有效需求重新生成方案。') }}
      </p>
      <p>
        {{
          tr('现金至少保留 {0}；每 {1} 秒检查一次。', [
            money(item.mission_request.policy.cash_floor_minor),
            item.mission_request.check_interval_seconds,
          ])
        }}
      </p>
      <p>{{ tr('这一步只建立跟进委托，每笔采购仍需你单独确认。') }}</p>
      <button
        class="primary"
        :disabled="
          s.busy ||
          !!s.pending ||
          item.demonstration ||
          simulationStale ||
          !shop.hasRole('operator')
        "
        @click="accept"
      >
        {{ tr('按这些条件开始跟进') }}
      </button>
      <p v-if="item.demonstration" class="source-note">
        {{ tr('模拟结果不能建立真实备货委托。') }}
      </p>
    </section>
  </template>
</template>
