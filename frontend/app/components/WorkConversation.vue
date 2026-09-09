<script setup lang="ts">
import { when } from '~/utils/presentation'
const work = useWorkItems(),
  { s } = work
const emit = defineEmits<{ changed: [] }>()
const log = ref<HTMLElement>()
async function send() {
  const d = await work.send()
  if (d) emit('changed')
}
async function resync() {
  await work.list()
  await work.load()
}
function keydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault()
    if (!s.busy && !s.pending && s.input.trim()) void send()
  }
}
watch(
  () => s.detail?.messages.length,
  async () => {
    await nextTick()
    if (log.value) log.value.scrollTop = log.value.scrollHeight
  },
)
</script>
<template>
  <aside class="agent-workspace glass work-conversation" aria-label="事项对话">
    <header class="agent-workspace-head">
      <div class="agent-monogram"><AppIcon name="sparkles" /></div>
      <div>
        <h2>一起处理这件事</h2>
        <p>补充、追问与结果保留在这里</p>
      </div>
    </header>
    <p v-if="!s.detail?.item.processor_available" class="notice">
      助手暂不可用。要求已保存，可以继续补充；已有备货操作仍可使用。
    </p>
    <p v-if="s.syncError || s.listError" class="notice amber" role="alert">
      {{ s.syncError || s.listError }}<button class="text-link" @click="resync">重新同步</button>
    </p>
    <div ref="log" class="work-message-log" role="log" aria-live="polite" aria-label="这件事的对话">
      <article
        v-for="message in s.detail?.messages"
        :key="message.id"
        class="agent-message"
        :class="{ 'is-user': message.role === 'user' }"
      >
        <div class="agent-message-byline">
          {{ message.role === 'user' ? '你' : message.role === 'system' ? '事项进展' : '助手'
          }}<time>{{ when(message.created_at) }}</time>
        </div>
        <small v-if="message.demonstration" class="tag amber">模拟接入</small>
        <p v-if="message.role !== 'assistant'" class="agent-user-text">{{ message.content }}</p>
        <MarkdownMessage v-else :content="message.content" />
        <details v-if="message.result">
          <summary>查看这次交付的结果</summary>
          <WorkResult :result="message.result" :demonstration="message.demonstration" />
        </details>
      </article>
    </div>
    <div class="work-composer">
      <label for="work-message">{{
        s.detail?.item.status === 'WAITING_INPUT' ? '补充这件事需要的信息' : '继续说说你的要求'
      }}</label>
      <textarea
        id="work-message"
        v-model="s.input"
        rows="3"
        maxlength="8000"
        :disabled="s.busy || !!s.pending"
        placeholder="可以补充条件，也可以继续追问…"
        @keydown="keydown"
      />
      <p v-if="s.error" class="notice amber" role="alert">{{ s.error }}</p>
      <div class="work-card-bottom">
        <small>{{
          s.detail?.item.status === 'PROCESSING'
            ? '新增要求会让旧的分析结果失效，已有业务动作不撤销。'
            : 'Enter 发送 · Shift+Enter 换行'
        }}</small
        ><button
          class="primary"
          :disabled="s.busy || (!s.pending && !s.input.trim())"
          @click="send"
        >
          {{ s.pending ? '查询并重试原提交' : '发送' }}
        </button>
      </div>
    </div>
  </aside>
</template>
