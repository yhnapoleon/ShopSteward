<script setup lang="ts">
import { t as tr } from '~/i18n'
const props = defineProps<{ issue: string | null; working: boolean; panel?: string }>()
const emit = defineEmits<{
  open: [name: string]
  confirm: []
  back: []
  navigate: [view: string]
  changed: []
}>()
const { s } = useWorkItems()
const route = useRoute()
// `panel=agent` (from the Agent entries) opens the conversation side on small screens.
const panel = computed(() => props.panel ?? (route.query.panel === 'agent' ? 'agent' : 'result'))
const item = computed(() => s.detail?.item)
</script>
<template>
  <!-- Every work item, with or without a restocking mission, uses the same workspace. -->
  <section v-if="item" class="work-detail" :data-work-id="item.id">
    <SpaceWorkspace
      :issue="issue"
      :working="working"
      :panel="panel"
      @open="emit('open', $event)"
      @confirm="emit('confirm')"
      @back="emit('back')"
      @navigate="emit('navigate', $event)"
      @changed="emit('changed')"
    />
  </section>
  <p v-else class="notice" role="status">{{ tr(s.syncError || '正在读取这件事…') }}</p>
</template>
