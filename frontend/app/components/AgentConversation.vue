<script setup lang="ts">
import type { Schema } from '~/types/models'
import type { ForecastReference } from '~/types/forecast'
import { when } from '~/utils/presentation'
const agent = useAgentConversation()
const { s, enabled, active } = agent
const { hasRole, mission, s: shopState } = useShop()
const router = useRouter()
const requestedForecast = useState<ForecastReference | null>('forecast-reference', () => null)
function forecastReferences(message: Schema<'MessageView'>) {
  return message.references.filter((r) => r.type === 'forecast' && typeof r.id === 'string')
}
async function openForecast(reference: Record<string, unknown>) {
  if (reference.store_id !== shopState.storeId || reference.sku_id !== mission.value?.sku_id) {
    s.error = '这条预测引用属于其他门店或商品，请切换到对应经营范围后查看。'
    return
  }
  const storeId = shopState.storeId
  const skuId = mission.value!.sku_id
  await router.push({ query: { view: 'today' } })
  await nextTick()
  if (storeId !== shopState.storeId || skuId !== mission.value?.sku_id) return
  requestedForecast.value = { id: String(reference.id), storeId, skuId, nonce: Date.now() }
}
const thread = ref<HTMLElement | null>(null),
  composer = ref<HTMLTextAreaElement | null>(null)
const newContent = ref(false),
  copied = ref('')
let copyTimer: ReturnType<typeof setTimeout> | undefined
const blocked = computed(
  () =>
    !enabled.value ||
    s.sending ||
    !!s.submission ||
    (!!active.value && s.run?.status !== 'WAITING_INPUT'),
)
function recordScroll() {
  if (!thread.value) return
  s.chatScrollTop = thread.value.scrollTop
  s.chatFollowing =
    thread.value.scrollHeight - thread.value.scrollTop - thread.value.clientHeight < 70
  if (s.chatFollowing) newContent.value = false
}
async function bottom() {
  await nextTick()
  if (thread.value) thread.value.scrollTop = thread.value.scrollHeight
  s.chatFollowing = true
  newContent.value = false
}
function resize() {
  if (composer.value) {
    composer.value.style.height = 'auto'
    composer.value.style.height = Math.min(composer.value.scrollHeight, 140) + 'px'
  }
}
function keydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault()
    if (!blocked.value && s.input.trim()) void agent.send()
  }
}
async function copy(id: string, text: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = id
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => (copied.value = ''), 1800)
  } catch {
    s.error = '无法复制，请选中文字复制。'
  }
}
function suggestion(text: string) {
  if (!blocked.value) {
    s.input = text
    composer.value?.focus()
  }
}
watch(
  () => s.messages.length + ':' + s.pending?.state,
  () => {
    if (s.chatFollowing) void bottom()
    else newContent.value = true
  },
)
watch(
  () => s.input,
  () => void nextTick(resize),
)
onMounted(() => {
  if (s.chatFollowing) void bottom()
  else if (thread.value) thread.value.scrollTop = s.chatScrollTop
  resize()
})
onUnmounted(() => clearTimeout(copyTimer))
</script>
<template>
  <section class="agent-conversation" aria-label="与Agent协作">
    <div class="agent-section-title">
      <h3>任务对话</h3>
      <span>围绕这项委托</span>
    </div>
    <div
      ref="thread"
      class="agent-thread"
      role="log"
      aria-label="任务对话"
      aria-live="polite"
      aria-relevant="additions"
      @scroll.passive="recordScroll"
    >
      <div v-if="!s.messages.length && !s.pending" class="agent-chat-empty">
        <AppIcon name="sparkles" />
        <p>可以问依据，也可以说出你的取舍。</p>
        <span>试算、调整方案与实际采购会分别呈现。</span>
      </div>
      <article
        v-for="m in s.messages"
        :key="m.id"
        class="agent-message"
        :class="{ 'is-user': m.role === 'user' }"
      >
        <div class="agent-message-byline">
          {{ m.role === 'user' ? '你' : 'ShopSteward' }}<time>{{ when(m.created_at) }}</time>
        </div>
        <p v-if="m.role === 'user'" class="agent-user-text">{{ m.content }}</p>
        <MarkdownMessage v-else :content="m.content" />
        <div v-if="forecastReferences(m).length" class="forecast-references">
          <button
            v-for="reference in forecastReferences(m)"
            :key="String(reference.id)"
            class="text-link"
            @click="openForecast(reference)"
          >
            查看预测依据 · {{ reference.version || reference.id }}
          </button>
        </div>
        <AgentReferences
          v-if="m.role === 'assistant'"
          :references="m.references || []"
          :run-id="m.run_id || undefined"
        />
        <div v-if="m.role === 'assistant'" class="agent-message-actions">
          <button class="text-link" @click="copy(m.id, m.content)">
            {{ copied === m.id ? '已复制' : '复制回答' }}</button
          ><button v-if="m.run_id" class="text-link" @click="agent.inspectRun(m.run_id)">
            查看本轮过程
          </button>
        </div>
      </article>
      <article v-if="s.pending" class="agent-message is-user pending-message">
        <div class="agent-message-byline">
          你<span>{{
            s.pending.state === 'sending'
              ? '正在发送'
              : s.pending.state === 'accepted'
                ? '已受理，正在同步'
                : '结果未确认'
          }}</span>
        </div>
        <p class="agent-user-text">{{ s.pending.content }}</p>
      </article>
    </div>
    <button v-if="newContent" class="agent-new-content" @click="bottom">
      有新内容 · 回到底部<AppIcon name="chevron-down" />
    </button>
    <div v-if="s.run?.status === 'WAITING_INPUT'" class="agent-clarification" role="status">
      <b>需要你补充</b>
      <p>{{ s.run.question }}</p>
    </div>
    <p v-if="s.error" class="notice amber" role="alert">{{ s.error }}</p>
    <button
      v-if="s.submission"
      class="secondary agent-retry"
      :disabled="s.sending"
      @click="agent.send"
    >
      查询或重试原消息
    </button>
    <p v-if="!enabled" class="channel-note">
      {{
        ['COMPLETED', 'CANCELLED'].includes(mission?.status || '')
          ? '委托已结束，可以回看原对话。'
          : 'Agent 暂未启用。当前可以核对方案、确认采购并跟进经营结果。'
      }}
    </p>
    <form class="agent-composer" @submit.prevent="agent.send">
      <label class="sr-only" for="agent-input">追问这项备货任务</label>
      <textarea
        id="agent-input"
        ref="composer"
        v-model="s.input"
        maxlength="8000"
        rows="2"
        :disabled="blocked"
        :placeholder="
          s.run?.status === 'WAITING_INPUT' ? '补充所需的信息…' : '问问依据，或说说你的取舍…'
        "
        @keydown="keydown"
      />
      <div class="agent-composer-foot">
        <span>Enter 发送 · Shift+Enter 换行</span
        ><button
          class="agent-send"
          :disabled="blocked || !s.input.trim()"
          aria-label="发送卡片内消息"
        >
          <AppIcon name="arrow-up" />
        </button>
      </div>
    </form>
    <div v-if="enabled" class="prompt-chips">
      <button :disabled="blocked" @click="suggestion('解释当前方案为什么推荐这个数量')">
        解释推荐依据</button
      ><button :disabled="blocked" @click="suggestion('如果本次最多买20件，会怎么样？先只试算。')">
        只试算 20 件
      </button>
    </div>
    <button
      v-if="s.conversation && hasRole('operator')"
      class="text-link agent-follow"
      :disabled="s.controlling"
      @click="agent.toggleFollowup"
    >
      Agent主动解读：{{ s.conversation.followup_enabled ? '已开启' : '未开启' }}
    </button>
  </section>
</template>
