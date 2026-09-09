<script setup lang="ts">
import { money, when } from '~/utils/presentation'
const props = defineProps<{ issue: string | null; working: boolean; panel?: string }>()
const emit = defineEmits<{
  open: [name: string]
  confirm: []
  back: []
  navigate: [view: string]
  changed: []
}>()
const work = useWorkItems(),
  { s } = work,
  shop = useShop()
const item = computed(() => s.detail?.item)
async function control(operation: 'cancel' | 'retry') {
  if (await work.control(operation)) emit('changed')
}
async function accept() {
  if (await work.acceptMission()) emit('changed')
}
const expired = computed(
  () =>
    item.value?.processing_expires_at && Date.parse(item.value.processing_expires_at) <= Date.now(),
)
</script>
<template>
  <section v-if="item" class="work-detail" :data-work-id="item.id">
    <TaskWorkspace
      v-if="item.mission_id && shop.mission.value?.id === item.mission_id"
      v-bind="props"
      @open="emit('open', $event)"
      @confirm="emit('confirm')"
      @back="emit('back')"
      @navigate="emit('navigate', $event)"
    >
      <template #assistant><WorkConversation @changed="emit('changed')" /></template>
      <template #intake>
        <div class="work-linked-summary glass">
          <div class="work-card-top">
            <b>{{ item.title }}</b
            ><span class="tag">{{ work.label(item) }}</span>
          </div>
          <p>{{ item.question || item.next_step || item.summary }}</p>
          <details v-if="item.result">
            <summary>这次讨论的结果</summary>
            <p
              v-if="['RECEIVED', 'PROCESSING', 'WAITING_INPUT'].includes(item.status)"
              class="notice"
            >
              这是之前的结果，尚未根据新要求更新。
            </p>
            <WorkResult :result="item.result" :demonstration="item.demonstration" />
          </details>
          <NuxtLink
            class="text-link"
            :to="{ query: { view: 'task', mission: item.mission_id, store: item.store_id } }"
            >此前的任务对话</NuxtLink
          >
        </div>
      </template>
    </TaskWorkspace>
    <template v-else>
      <button class="task-back text-link" @click="emit('back')">
        <AppIcon name="arrow-right" />返回今日
      </button>
      <header class="work-heading">
        <div>
          <span class="eyebrow">我的事项</span>
          <h1>{{ item.title }}</h1>
        </div>
        <span class="tag" role="status">{{ work.label(item) }}</span>
      </header>
      <div class="work-detail-grid">
        <div class="work-result-column">
          <section class="glass work-status-panel">
            <h2>
              {{
                item.status === 'WAITING_INPUT'
                  ? '还需要你补充'
                  : item.status === 'RECEIVED'
                    ? '这件事已经收到'
                    : '当前进展'
              }}
            </h2>
            <p>{{ item.question || item.summary || '原始要求已保存，可以在右侧继续补充。' }}</p>
            <p>{{ item.next_step }}</p>
            <small>最近更新：{{ when(item.updated_at) }}</small>
            <p v-if="expired" class="notice amber">
              本轮处理未按时返回，可以重试；已保存的内容仍保留。
            </p>
          </section>
          <section v-if="item.result" class="glass work-status-panel">
            <p
              v-if="['RECEIVED', 'PROCESSING', 'WAITING_INPUT'].includes(item.status)"
              class="notice"
            >
              这是之前的结果，尚未根据新要求更新。
            </p>
            <WorkResult :result="item.result" :demonstration="item.demonstration" />
          </section>
          <section v-if="item.mission_request" class="glass work-status-panel">
            <h2>开始持续跟进这项备货</h2>
            <p>{{ item.mission_request.objective }}</p>
            <p>
              现金至少保留 {{ money(item.mission_request.policy.cash_floor_minor) }}；每
              {{ item.mission_request.check_interval_seconds }} 秒检查。
            </p>
            <p>这一步只建立跟进委托，每笔采购仍需你单独确认。</p>
            <button
              class="primary"
              :disabled="s.busy || !!s.pending || item.demonstration || !shop.hasRole('operator')"
              @click="accept"
            >
              按这些条件开始跟进
            </button>
            <p v-if="item.demonstration" class="source-note">模拟结果不能建立真实备货委托。</p>
          </section>
        </div>
        <WorkConversation @changed="emit('changed')" />
      </div>
    </template>
    <footer class="work-controls">
      <button
        v-if="['RECEIVED', 'PROCESSING', 'WAITING_INPUT'].includes(item.status)"
        class="text-link"
        :disabled="s.busy || !!s.pending"
        @click="control('cancel')"
      >
        停止本轮处理</button
      ><button
        v-if="['BLOCKED', 'CANCELLED'].includes(item.status) || expired"
        class="secondary"
        :disabled="s.busy || !!s.pending"
        @click="control('retry')"
      >
        重新处理这件事</button
      ><span>停止助手处理不等于停止备货跟进或取消采购。</span>
    </footer>
  </section>
  <p v-else class="notice" role="status">{{ s.syncError || '正在读取这件事…' }}</p>
</template>
