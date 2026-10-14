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
      <AgentWorkspace @target="emit('target', $event)" />
    </div>
    <div v-show="tab === 'work'" class="space-conversation-pane">
      <WorkConversation @changed="emit('changed')" />
    </div>
  </div>
</template>
