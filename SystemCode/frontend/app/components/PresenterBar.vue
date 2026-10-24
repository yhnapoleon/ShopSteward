<script setup lang="ts">
import { t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { api, ApiFailure, query } from '~/utils/api'
import { money, number, when } from '~/utils/presentation'

// The presenter bar (workspace redesign §10): demo mode only, desktop widths only. A small capsule
// in the bottom-right corner: the business time, "Next event" and a menu for the rarer controls.
// "Next event" runs the existing simulator advance, then waits until the business state version
// moves (at most 90 s, with the same pulse as the sync strip) and says in one sentence what the
// newest ledger entries changed. It sets no figure itself; the bar only asks the page to open or
// navigate.
const emit = defineEmits<{ open: [name: string]; navigate: [view: string] }>()
const route = useRoute()
const shop = useShop()
const { s, stock } = shop
const demo = useDemoMode()
// The marker the sync strips pulse on: the state version the page is waiting to move from.
const marker = useState('space-sync-advance', () => ({ from: null as number | null, until: 0 }))
// A note keeps its id across a language switch, so only a new message fades in.
type Note = {
  id: string
  tone: 'progress' | 'done' | 'wait' | 'error' | 'info'
  text: () => string
}
const phase = ref<'idle' | 'advancing' | 'syncing' | 'creating'>('idle')
const result = ref<Note | null>(null)
let alive = true,
  attempt = 0,
  expiry: ReturnType<typeof setTimeout> | undefined

const visible = computed(() => demo.enabled.value && !!s.session?.authenticated)
// Why "next event" cannot run; nothing is claimed while the store is still being read.
const blocked = computed(() =>
  s.loading
    ? ''
    : !s.session?.devTools
      ? '当前身份没有开发权限，不能推进或新建示例店铺。'
      : !s.storeId
        ? '先新建一家示例店铺。'
        : !s.runs[s.storeId]
          ? '这家店铺没有本浏览器的推进记录，可以新建示例店铺再演示。'
          : '',
)
const busy = computed(() => phase.value !== 'idle' || !!s.busy || s.loading)
const note = computed<Note | null>(() => {
  if (phase.value === 'advancing')
    return { id: 'advancing', tone: 'progress', text: () => tr('正在推进下一个经营事件') }
  if (phase.value === 'syncing')
    return { id: 'syncing', tone: 'progress', text: () => tr('后台正在同步经营数据') }
  if (phase.value === 'creating')
    return { id: 'creating', tone: 'progress', text: () => tr('正在创建示例店铺') }
  if (result.value) return result.value
  if (blocked.value && phase.value === 'idle') {
    const reason = blocked.value
    return { id: 'blocked:' + reason, tone: 'info', text: () => tr(reason) }
  }
  return null
})
const clock = computed(() => s.dashboard?.state.simulation_time || '')

// The menu closes on a choice or on Escape, with focus back on its button (so a dialog opened from
// it returns focus there), and on a press outside it.
const menu = ref<HTMLDetailsElement>()
function close(refocus = false) {
  if (!menu.value?.open) return
  menu.value.open = false
  if (refocus) menu.value.querySelector('summary')?.focus()
}
function escape(event: KeyboardEvent) {
  if (!menu.value?.open) return
  event.stopPropagation()
  close(true)
}
function outside(event: PointerEvent) {
  if (!menu.value?.contains(event.target as Node)) close()
}
function toggled() {
  if (menu.value?.open) document.addEventListener('pointerdown', outside)
  else document.removeEventListener('pointerdown', outside)
}

let shown = 0
function show(tone: Note['tone'], text: () => string, hold = 20000) {
  result.value = { id: 'result:' + ++shown, tone, text }
  clearTimeout(expiry)
  if (hold) expiry = setTimeout(() => (result.value = null), hold)
}
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
// The notice useShop().advance() leaves for pages without the bar.
const ADVANCED = '模拟器事件已推进；后台正在同步并复查。'

/** One sentence for the ledger entries newer than `from`, led by the newest entry's kind. */
function describe(from: number | null, demandBefore: number | null): () => string {
  const fresh = s.ledger.filter((e) => from === null || e.state_version > from)
  const latest = fresh[0]
  if (!latest) return () => tr('经营数据已更新')
  const same = fresh.filter((e) => e.effect_type === latest.effect_type)
  const total = (pick: (c: Schema<'LedgerChanges'>) => number) =>
    same.reduce((n, e) => n + (e.changes ? pick(e.changes) : 0), 0)
  if (latest.effect_type === 'GOODS_RECEIVED') {
    const received = total((c) => c.on_hand_delta)
    return () => tr('到货已核实：在库 +{0}', [number(received)])
  }
  if (latest.effect_type === 'SALE_RECORDED') {
    const sold = -total((c) => c.on_hand_delta),
      receivable = total((c) => c.receivables_delta_minor)
    return () => tr('售出 {0} 件，待结算 +{1}', [number(sold), money(receivable)])
  }
  if (latest.effect_type === 'DEMAND_REVISED') {
    // The ledger's four deltas stay 0 for a demand revision; the dashboard says before and after.
    const after = stock.value?.remaining_demand ?? latest.remaining_demand_after
    return demandBefore != null && after != null && after !== demandBefore
      ? () => tr('需求已修订：{0}→{1} 件', [number(demandBefore), number(after)])
      : () => tr('需求已修订')
  }
  if (latest.effect_type === 'PURCHASE_ACCEPTED') return () => tr('采购已受理')
  return () => tr('经营数据已更新')
}

function failure(error: unknown) {
  const message = (error as Error)?.message || ''
  // A finished background job that could not advance reports only a generic worker message.
  if (
    !(error instanceof ApiFailure) &&
    /Worker handler did not complete|后台任务未完成/.test(message)
  )
    return '这一步没有推进。可能还没有在途采购可以到货，或这一轮示例已经走完。'
  return message || '这一步没有推进。可能还没有在途采购可以到货，或这一轮示例已经走完。'
}

async function nextEvent() {
  if (busy.value || blocked.value) return
  const id = ++attempt,
    storeId = s.storeId,
    from = s.dashboard?.state.state_version ?? null,
    demandBefore = stock.value?.remaining_demand ?? null
  const current = () => alive && id === attempt && s.storeId === storeId
  result.value = null
  phase.value = 'advancing'
  marker.value = { from, until: Date.now() + 90000 }
  try {
    await shop.advance()
    // The bar reports this step itself; the page's generic notice would say it a second time.
    if (shop.s.notice === ADVANCED) shop.s.notice = ''
  } catch (error) {
    if (!current()) return
    phase.value = 'idle'
    marker.value = { from: null, until: 0 }
    const message = failure(error)
    show('error', () => tr(message), 0)
    return
  }
  if (!current()) return
  phase.value = 'syncing'
  const deadline = Date.now() + 90000
  while (
    current() &&
    (s.dashboard?.state.state_version ?? null) === from &&
    Date.now() < deadline
  ) {
    await pause(1200)
    if (!current()) break
    try {
      const board = await api<Schema<'Dashboard'>>(
        '/api/v1/dashboard' + query({ store_id: storeId }),
      )
      if (current() && board.state.state_version !== from) await shop.refresh(true)
    } catch {
      // Keep waiting; the page reports a lost connection by itself.
    }
  }
  if (!current()) return
  phase.value = 'idle'
  if ((s.dashboard?.state.state_version ?? null) === from) {
    show('wait', () => tr('后台仍在同步，数据稍后会自动更新。'))
    return
  }
  show('done', describe(from, demandBefore))
}

async function createStore() {
  if (busy.value || !s.session?.devTools) return
  const id = ++attempt
  result.value = null
  phase.value = 'creating'
  try {
    await shop.createScenario()
  } catch (error) {
    if (alive && id === attempt) {
      const message = (error as Error).message
      show('error', () => tr(message), 0)
    }
  } finally {
    if (alive && id === attempt) phase.value = 'idle'
  }
}

// A store change (switching, or a new sample store) ends any wait that belonged to the old one.
watch(
  () => s.storeId,
  () => {
    if (phase.value === 'creating') return
    attempt++
    phase.value = 'idle'
    result.value = null
  },
)
// Remember creation times of sample stores seen in demo mode, for naming them in the store list.
watch(
  () => [demo.enabled.value, s.storeId, s.ledger.find((e) => e.effect_type === 'INIT')?.id],
  ([on]) => {
    if (on) demo.remember()
  },
  { immediate: true },
)
onUnmounted(() => {
  document.removeEventListener('pointerdown', outside)
  alive = false
  attempt++
  clearTimeout(expiry)
})
</script>
<template>
  <div
    v-if="visible"
    class="presenter-bar"
    role="region"
    :aria-label="tr('演示控制')"
    :data-phase="phase"
  >
    <div class="presenter-note-slot" role="status">
      <Transition name="presenter-note" mode="out-in">
        <p v-if="note" :key="note.id" class="presenter-note" :class="note.tone">
          <span v-if="note.tone === 'progress'" class="presenter-pulse" aria-hidden="true" />{{
            note.text()
          }}
        </p>
      </Transition>
    </div>
    <div class="presenter-clock">
      <small>{{ tr('经营时点') }}</small>
      <span class="presenter-clock-value"
        ><Transition name="presenter-tick" mode="out-in"
          ><b :key="clock">{{ tr(when(clock || null)) }}</b></Transition
        ></span
      >
    </div>
    <button
      class="secondary presenter-next"
      :disabled="busy || !!blocked"
      :title="blocked ? tr(blocked) : undefined"
      @click="nextEvent"
    >
      <template v-if="phase === 'advancing' || phase === 'syncing'"
        ><AppIcon name="loader-circle" class="presenter-spin" />{{
          tr(phase === 'advancing' ? '正在推进…' : '正在同步…')
        }}</template
      ><template v-else>{{ tr('推进一个经营事件') }}<AppIcon name="play" /></template>
    </button>
    <details ref="menu" class="presenter-more" @toggle="toggled" @keydown.esc="escape">
      <summary
        class="presenter-action"
        :aria-label="tr('更多演示操作')"
        :title="tr('更多演示操作')"
      >
        <AppIcon name="ellipsis" />
      </summary>
      <div class="presenter-menu" @click="close(true)">
        <button
          class="presenter-action"
          :disabled="busy || !s.session?.devTools"
          @click="createStore"
        >
          <AppIcon name="plus" />{{ tr('新建示例店铺') }}
        </button>
        <button class="presenter-action" :disabled="busy" @click="emit('open', 'controls')">
          <AppIcon name="layers-2" />{{ tr('切换店铺') }}
        </button>
        <button
          class="presenter-action"
          :class="{ active: route.query.view === 'overview' }"
          :aria-current="route.query.view === 'overview' ? 'page' : undefined"
          @click="emit('navigate', 'overview')"
        >
          <AppIcon name="chart-no-axes-combined" />{{ tr('经营概览') }}
        </button>
      </div>
    </details>
  </div>
</template>
