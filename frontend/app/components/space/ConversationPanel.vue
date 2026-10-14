<script setup lang="ts">
import { t as tr } from '~/i18n'

// The conversation side of the workspace (§4.3): the mission's Agent and the item's own
// conversation. Both stay mounted so switching never loses a draft or a running stream.
const emit = defineEmits<{ target: [name: string]; changed: [] }>()
const route = useRoute()
const { s } = useShop()
const agent = useAgentConversation()
const { item, linked } = useSpace()
const chosen = ref<'agent' | 'work' | null>(route.query.panel === 'agent' ? 'agent' : null)
// Default: the Agent when it is enabled, or when this mission already has Agent history to show
// (a failed or waiting run must stay visible); otherwise the item's own conversation.
const tab = computed(() =>
  !linked.value
    ? 'work'
    : (chosen.value ??
      (s.session?.agentEnabled || agent.s.run || agent.s.messages.length ? 'agent' : 'work')),
)
watch(
  () => route.query.panel,
  (panel) => {
    if (panel === 'agent') chosen.value = 'agent'
  },
)
watch(
  () => item.value?.id,
  (id, before) => {
    if (before && id !== before) chosen.value = route.query.panel === 'agent' ? 'agent' : null
  },
)
function show(next: 'agent' | 'work') {
  chosen.value = next
}
defineExpose({ show })
// Memories the Agent formed in this conversation while the page was open (§8). The drawer's
// owner detects them; here they become one line at the top of the Agent conversation.
const memory = useAgentKnowledge()
const remembered = computed(() =>
  memory.s.receipt.scope && memory.s.receipt.scope === agent.s.scope ? memory.s.receipt.count : 0,
)
</script>
<template>
  <div class="space-conversation">
    <div v-if="linked" class="space-segment" role="group" :aria-label="tr('选择对话')">
      <button :aria-pressed="tab === 'agent'" @click="show('agent')">
        {{ tr('Agent 对话')
        }}<span
          v-if="agent.active.value"
          class="agent-live-dot"
          :class="{ 'is-running': agent.running.value }"
        />
      </button>
      <button :aria-pressed="tab === 'work'" @click="show('work')">{{ tr('事项对话') }}</button>
    </div>
    <div v-if="linked" v-show="tab === 'agent'" class="space-conversation-pane">
      <div class="memory-receipt-slot" role="status">
        <Transition name="space-rise">
          <p v-if="remembered" class="memory-receipt">
            <AppIcon name="sparkles" /><span>{{
              remembered === 1 ? tr('Agent 更新了一条记忆') : tr('Agent 更新了 {0} 条记忆', [remembered])
            }}</span
            ><span aria-hidden="true">·</span
            ><button
              class="text-link"
              aria-haspopup="dialog"
              @click="memory.show($event.currentTarget)"
            >
              {{ tr('查看记忆') }}
            </button>
          </p>
        </Transition>
      </div>
      <AgentWorkspace @target="emit('target', $event)" />
    </div>
    <div v-show="tab === 'work'" class="space-conversation-pane">
      <WorkConversation @changed="emit('changed')" />
    </div>
  </div>
</template>
