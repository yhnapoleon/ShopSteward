<script setup lang="ts">
import { t as tr } from '~/i18n'
import { when } from '~/utils/presentation'
import { firstSync } from '~/utils/glossary'

// One line on how current the facts are. Routine polling is quick and stays silent; the pulse
// appears only for a slow refresh, or after a simulated event until the state version moves.
// The strip names one time, the business time; when the data was last synced sits behind the
// state (hover) and on the facts card's note, so the two are never read as one clock.
// `compact` is the today page's side column.
defineProps<{ compact?: boolean }>()
const { s } = useShop()
const advance = useState('space-sync-advance', () => ({ from: null as number | null, until: 0 }))
const slow = ref(false)
const now = ref(Date.now())
let slowTimer: ReturnType<typeof setTimeout> | undefined
let clock: ReturnType<typeof setInterval> | undefined
watch(
  () => s.refreshing,
  (refreshing) => {
    clearTimeout(slowTimer)
    if (!refreshing) slow.value = false
    else slowTimer = setTimeout(() => (slow.value = s.refreshing), 700)
  },
  { immediate: true },
)
watch(
  () => s.busy,
  (busy) => {
    if (busy === '正在推进经营事件')
      advance.value = {
        from: s.dashboard?.state.state_version ?? null,
        until: Date.now() + 90000,
      }
  },
)
watch(
  () => s.dashboard?.state.state_version,
  (version) => {
    if (advance.value.from !== null && version !== advance.value.from) advance.value.from = null
  },
)
const waiting = computed(
  () =>
    advance.value.from !== null &&
    now.value < advance.value.until &&
    s.dashboard?.state.state_version === advance.value.from,
)
watch(
  () => advance.value.from,
  (from) => {
    clearInterval(clock)
    if (from === null) return
    now.value = Date.now()
    clock = setInterval(() => (now.value = Date.now()), 1000)
  },
  { immediate: true },
)
onUnmounted(() => {
  clearTimeout(slowTimer)
  clearInterval(clock)
})
// A new store's first sync is still running: the strip says so, like the card above it.
const syncing = computed(
  () => s.connected && (slow.value || waiting.value || firstSync(s.dashboard?.freshness)),
)
</script>
<template>
  <div class="space-sync" :class="{ 'is-compact': compact }" :aria-label="tr('数据同步状态')">
    <span class="space-sync-item"
      ><AppIcon name="clock" />{{
        tr('经营时点 {0}', [when(s.dashboard?.state.simulation_time)])
      }}</span
    ><span
      class="space-sync-state"
      :class="{ 'is-syncing': syncing, 'is-off': !s.connected }"
      role="status"
      :title="tr('数据同步 {0}', [when(s.dashboard?.freshness.last_sync_at)])"
      ><span class="space-pulse" aria-hidden="true" />{{
        tr(syncing ? '后台正在同步' : s.connected ? '已同步' : '连接中断，显示上次数据')
      }}</span
    >
  </div>
</template>
