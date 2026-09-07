<script setup lang="ts">
import type { Schema } from '~/types/models'
import { api } from '~/utils/api'
const { s, mission, refresh, hasRole } = useShop()
const messages = ref<Schema<'MessageView'>[]>([]),
  conversation = ref<Schema<'ConversationView'> | null>(null),
  run = ref<Schema<'RunView'> | null>(null),
  input = ref(''),
  error = ref(''),
  sending = ref(false)
let timer: ReturnType<typeof setInterval> | undefined,
  version = 0,
  reading = false
const active = computed(
  () => run.value && ['QUEUED', 'RUNNING', 'WAITING_INPUT'].includes(run.value.status),
)
const enabled = computed(() => Boolean(s.session?.agentEnabled && mission.value))
async function load() {
  if (!mission.value || !s.session?.authenticated || reading) return
  reading = true
  const id = mission.value!.id,
    v = version
  try {
    const list = await api<Schema<'ConversationList'>>(
      `/api/v1/missions/${id}/conversations?limit=100`,
    )
    const c = list.items.find((c) => c.is_default) || list.items[0]
    if (v !== version) return
    if (!c) {
      conversation.value = null
      return
    }
    conversation.value = c
    const all: Schema<'MessageView'>[] = []
    let after = 0
    for (let i = 0; i < 10; i++) {
      const page = await api<Schema<'MessageList'>>(
        `/api/v1/conversations/${c.id}/messages?limit=100&after_seq=${after}`,
      )
      all.push(...page.items)
      if (page.next_after_seq === null) break
      after = page.next_after_seq
    }
    if (v !== version) return
    messages.value = all
    const rid = c.active_run_id || run.value?.id
    if (rid) {
      const next = await api<Schema<'RunView'>>('/api/v1/agent-runs/' + rid)
      if (v !== version) return
      const done = run.value?.status !== next.status && next.status === 'SUCCEEDED'
      run.value = next
      if (done) await refresh(true)
    }
  } catch (e) {
    if (v === version) error.value = (e as Error).message
  } finally {
    reading = false
  }
}
watch(
  () => mission.value?.id,
  () => {
    version++
    messages.value = []
    run.value = null
    conversation.value = null
    error.value = ''
    void load()
  },
)
onMounted(() => {
  void load()
  timer = setInterval(() => void load(), 2500)
})
onUnmounted(() => {
  version++
  if (timer) clearInterval(timer)
})
async function send() {
  const content = input.value.trim()
  if (!content || !enabled.value || sending.value) return
  sending.value = true
  error.value = ''
  try {
    if (!conversation.value)
      conversation.value = await api<Schema<'ConversationView'>>(
        `/api/v1/missions/${mission.value!.id}/conversations`,
        'POST',
        { is_default: true, title: '活动备货' },
      )
    let id: string
    if (run.value?.status === 'WAITING_INPUT') {
      const r = await api<Schema<'ResumeAccepted'>>(
        `/api/v1/agent-runs/${run.value.id}/resume`,
        'POST',
        { interrupt_id: run.value.interrupt_id, content },
      )
      id = r.agent_run_id
    } else {
      const r = await api<Schema<'MessageAccepted'>>(
        `/api/v1/conversations/${conversation.value.id}/messages`,
        'POST',
        { content },
      )
      id = r.agent_run_id
    }
    input.value = ''
    run.value = await api<Schema<'RunView'>>('/api/v1/agent-runs/' + id)
    await load()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    sending.value = false
  }
}
async function cancel() {
  if (!run.value) return
  try {
    run.value = await api<Schema<'RunView'>>(
      `/api/v1/agent-runs/${run.value.id}/cancel`,
      'POST',
      {},
    )
    await load()
  } catch (e) {
    error.value = (e as Error).message
  }
}
async function toggleFollowup() {
  if (!conversation.value) return
  try {
    conversation.value = await api<Schema<'ConversationView'>>(
      `/api/v1/conversations/${conversation.value.id}/followup`,
      'PATCH',
      {
        enabled: !conversation.value.followup_enabled,
        interval_seconds: 300,
        expected_version: conversation.value.followup_version,
      },
    )
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>
<template>
  <div class="card-conversation">
    <p v-if="!enabled" class="channel-note">
      Agent 暂未启用。当前可以查看真实方案、确认采购并跟进经营结果。
    </p>
    <div
      v-if="messages.length"
      class="chat-thread"
      role="log"
      aria-label="任务对话"
      aria-live="polite"
    >
      <div v-for="m in messages" :key="m.id" class="bubble" :class="{ user: m.role === 'user' }">
        <div v-if="m.role === 'assistant'" class="bubble-label">ShopSteward</div>
        {{ m.content }}
      </div>
    </div>
    <p v-if="run?.status === 'WAITING_INPUT'" class="notice">{{ run.question }}</p>
    <p v-else-if="active" role="status" class="channel-note">
      {{ run?.status === 'QUEUED' ? '等待Agent处理…' : '正在处理…'
      }}<button class="text-link" @click="cancel">停止本轮回答</button>
    </p>
    <p v-if="run?.status === 'FAILED'" class="notice amber">
      这次回答未完成：{{ run.error_code }}。经营记录仍然保留。
    </p>
    <p v-if="error" class="notice amber" role="alert">{{ error }}</p>
    <form class="composer" @submit.prevent="send">
      <label class="sr-only" for="agent-input">追问这项备货任务</label
      ><input
        id="agent-input"
        v-model="input"
        maxlength="8000"
        :disabled="!enabled || sending || (!!active && run?.status !== 'WAITING_INPUT')"
        :placeholder="
          run?.status === 'WAITING_INPUT' ? '补充所需的信息…' : '问问依据，或说说你的取舍…'
        "
      /><button type="button" class="icon-btn" disabled aria-label="语音入口尚未开放">
        <AppIcon name="mic" /></button
      ><button
        class="icon-btn send"
        :disabled="
          !enabled || sending || !input.trim() || (!!active && run?.status !== 'WAITING_INPUT')
        "
        aria-label="发送卡片内消息"
      >
        <AppIcon name="arrow-up" />
      </button>
    </form>
    <div v-if="enabled" class="prompt-chips">
      <button @click="input = '解释当前方案为什么推荐这个数量'">为什么推荐这个数量？</button
      ><button @click="input = '如果本次最多买20件，会怎么样？先只试算。'">如果只补20件呢？</button
      ><button @click="input = '下一次什么时候检查？'">下一次检查</button>
    </div>
    <button
      v-if="conversation && hasRole('operator')"
      class="text-link agent-follow"
      @click="toggleFollowup"
    >
      Agent主动解读：{{ conversation.followup_enabled ? '已开启' : '未开启' }}
    </button>
  </div>
</template>
