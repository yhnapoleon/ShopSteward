<script setup lang="ts">
import { t as tr } from '~/i18n'
import { when } from '~/utils/presentation'
const work = useWorkItems(),
  { s } = work
const emit = defineEmits<{ changed: [] }>()
const log = ref<HTMLElement>()
// An emergency restock under way on this item's mission leads the page with its own card.
const { mission } = useSpace()
const launcher = useRecoveryLaunch()
const restocking = computed(() => launcher.inProgress(mission.value?.id))
// Item whose message was just saved while no assistant can process it. The receipt below the
// messages appears once (240ms fade) and stays; further messages do not replay it.
const saved = ref('')
watch(
  () => s.detail?.item.id,
  (id) => {
    if (id !== saved.value) saved.value = ''
  },
)
// Lines the system wrote are fixed sentences and follow the language: its own notes, and the
// request a quantity trial records just before its result. What the owner typed stays as written.
const written = (index: number) => {
  const messages = s.detail?.messages || []
  const message = messages[index]
  return (
    message?.role === 'system' ||
    (message?.role === 'user' && !!messages[index + 1]?.result?.calculation)
  )
}
// Translated lines read naturally in English: a trial's quantities are listed with commas, not 、.
const shown = (content: string) => {
  const english = tr(content)
  return english === content ? content : english.replace(/、/g, ', ')
}
// A quantity trial's explanation is the system's own text, read line by line as its result card
// does (surfaces/derive.ts).
const explained = (content: string) =>
  content
    .split('\n')
    .map((line) => tr(line))
    .join('\n')
async function send() {
  const message = s.pending ? s.pending.path.endsWith('/messages') : !!s.input.trim()
  const d = await work.send()
  if (!d) return
  if (message && !d.item.processor_available) saved.value = d.item.id
  emit('changed')
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
  <aside class="agent-workspace glass work-conversation" :aria-label="tr('事项对话')">
    <header class="agent-workspace-head">
      <div class="agent-monogram"><AppIcon name="sparkles" /></div>
      <div>
        <h2>{{ tr('一起处理这件事') }}</h2>
        <p>{{ tr('补充、追问与结果保留在这里') }}</p>
      </div>
    </header>
    <!-- While an emergency restock leads the page its card says everything; the conversation
         keeps quiet about what it cannot do. -->
    <p v-if="!s.detail?.item.processor_available && !restocking" class="notice">
      {{
        tr(
          s.detail?.item.result?.calculation
            ? '试算已完成，可以调整条件继续比较；现在没有助手回复。'
            : '现在没有助手回复。你写的内容会保存在这件事里，备货操作照常可用。',
        )
      }}
    </p>
    <p v-if="s.syncError || s.listError" class="notice amber" role="alert">
      {{ tr(s.syncError || s.listError)
      }}<button class="text-link" @click="resync">{{ tr('重新同步') }}</button>
    </p>
    <div
      ref="log"
      class="work-message-log"
      role="log"
      aria-live="polite"
      :aria-label="tr('这件事的对话')"
    >
      <article
        v-for="(message, index) in s.detail?.messages"
        :key="message.id"
        class="agent-message"
        :class="{ 'is-user': message.role === 'user' }"
      >
        <div class="agent-message-byline">
          {{
            tr(
              message.role === 'user'
                ? '你'
                : message.role === 'system'
                  ? '事项进展'
                  : message.result?.calculation
                    ? '试算结果'
                    : '助手',
            )
          }}<time>{{ tr(when(message.created_at)) }}</time>
        </div>
        <small v-if="message.demonstration" class="tag amber">{{ tr('模拟接入') }}</small>
        <p v-if="message.role !== 'assistant'" class="agent-user-text">
          {{ written(index) ? shown(message.content) : message.content }}
        </p>
        <MarkdownMessage
          v-else
          :content="message.result?.calculation ? explained(message.content) : message.content"
        />
        <details v-if="message.result">
          <summary>{{ tr('查看这次交付的结果') }}</summary>
          <WorkResult :result="message.result" :demonstration="message.demonstration" />
        </details>
      </article>
    </div>
    <div class="work-saved-slot" role="status">
      <Transition name="space-appear">
        <p
          v-if="saved && saved === s.detail?.item.id && !s.detail?.item.processor_available"
          class="work-saved"
        >
          <AppIcon name="check" /><span>{{
            tr('已保存。助手启用后会处理；现在可以继续补充，或用卡片完成操作。')
          }}</span>
        </p>
      </Transition>
    </div>
    <div class="work-composer">
      <QuotationUpload v-if="!restocking" @changed="emit('changed')" />
      <label for="work-message">{{
        tr(s.detail?.item.status === 'WAITING_INPUT' ? '补充这件事需要的信息' : '继续说说你的要求')
      }}</label>
      <textarea
        id="work-message"
        v-model="s.input"
        rows="3"
        maxlength="8000"
        :disabled="s.busy || !!s.pending"
        :placeholder="tr('可以补充条件，也可以继续追问…')"
        @keydown="keydown"
      />
      <p v-if="s.error" class="notice amber" role="alert">{{ tr(s.error) }}</p>
      <div class="work-card-bottom">
        <small>{{
          tr(
            s.detail?.item.status === 'PROCESSING'
              ? '新增要求会让旧的分析结果失效，已有业务动作不撤销。'
              : 'Enter 发送 · Shift+Enter 换行',
          )
        }}</small
        ><button
          class="primary"
          :disabled="s.busy || (!s.pending && !s.input.trim())"
          @click="send"
        >
          {{ tr(s.pending ? '查询并重试原提交' : '发送') }}
        </button>
      </div>
    </div>
  </aside>
</template>
