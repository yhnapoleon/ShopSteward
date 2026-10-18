<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { api, query } from '~/utils/api'
import { actionLabel, when } from '~/utils/presentation'
import { groupTimeline } from '~/utils/timeline'

// The mission's history in the owner's words (§7): six rows, routine checks folded, then the
// earlier rows and every plan version with the decisions taken on it.
const emit = defineEmits<{ open: [name: string] }>()
const shop = useShop()
const { s } = shop
const space = useSpace()
const { mission, actions } = space
const rows = computed(() => groupTimeline(s.timeline))
const recent = computed(() => rows.value.slice(0, 6))
const earlier = computed(() => rows.value.slice(6))
const error = ref('')
const plans = ref<Schema<'Plan'>[]>([])
const plansLoaded = ref(false)
const plansError = ref('')
const plansCursor = ref<string | null>(null)
const plansLoading = ref(false)
let epoch = 0
watch(
  () => mission.value?.id,
  () => {
    epoch++
    plans.value = []
    plansLoaded.value = false
    plansError.value = ''
    plansCursor.value = null
    plansLoading.value = false
    error.value = ''
  },
)
onUnmounted(() => epoch++)
async function toggled(e: Event) {
  if ((e.target as HTMLDetailsElement).open && !plansLoaded.value) await loadPlans()
}
async function loadPlans() {
  if (!mission.value || plansLoading.value) return
  const id = mission.value.id,
    n = epoch
  plansLoading.value = true
  plansError.value = ''
  try {
    const page = await api<Schema<'PlanList'>>(
      `/api/v1/missions/${id}/plans${query({ limit: 100, cursor: plansCursor.value })}`,
    )
    if (n !== epoch) return
    plans.value = [...new Map([...plans.value, ...page.items].map((p) => [p.id, p])).values()]
    plansCursor.value = page.next_cursor
    plansLoaded.value = true
  } catch (e) {
    if (n === epoch) plansError.value = (e as Error).message
  } finally {
    if (n === epoch) plansLoading.value = false
  }
}
async function more() {
  error.value = ''
  try {
    await shop.moreTimeline()
  } catch (e) {
    error.value = (e as Error).message
  }
}
const planStatus: Record<string, string> = {
  PENDING_APPROVAL: '待你确认',
  APPROVED: '你确认了采购',
  REJECTED: '本轮不采购',
  SUPERSEDED: '已被后续方案取代',
  EXPIRED: '已过期',
}
</script>
<template>
  <section
    id="space-history"
    class="task-history space-target space-history"
    :class="{ 'target-active': space.isTarget('history') }"
  >
    <div class="task-section-heading">
      <h2>{{ tr('委托记录') }}</h2>
      <button
        class="text-link"
        :aria-label="tr('本次经营简报 已做的决定、实际结果与下一步')"
        @click="emit('open', 'brief')"
      >
        {{ tr('保存经营简报') }}<AppIcon name="file-text" />
      </button>
    </div>
    <ol class="space-timeline">
      <template v-for="row in recent" :key="row.key"
        ><li v-if="row.kind === 'group'" class="space-timeline-row is-group">
          <span class="space-timeline-mark" :class="row.tone" aria-hidden="true"
            ><span class="timeline-dot"
          /></span>
          <details class="space-timeline-group">
            <summary>{{ row.label }}</summary>
            <p v-for="entry in row.items" :key="entry.entry.id">
              {{ `${when(entry.entry.created_at)} · ${entry.event.title}` }}
            </p>
          </details>
        </li>
        <li v-else class="space-timeline-row">
          <span
            class="space-timeline-mark"
            :class="[row.event.tone, { 'is-owner': row.event.icon === 'user' }]"
            aria-hidden="true"
            ><AppIcon v-if="row.event.icon === 'user'" name="user" /><span
              v-else
              class="timeline-dot"
          /></span>
          <div>
            <p>{{ row.event.title }}</p>
            <small v-if="row.event.detail">{{ row.event.detail }}</small>
            <time>{{
              joinText(
                [
                  tr(when(row.entry.created_at)),
                  '·',
                  tr(row.event.icon === 'user' ? '用户决定' : '系统记录'),
                ],
                ' ',
              )
            }}</time>
          </div>
        </li></template
      >
    </ol>
    <p v-if="!rows.length" class="source-note">{{ tr('还没有这类记录。') }}</p>
    <details v-if="earlier.length || s.timelineCursor" class="task-earlier">
      <summary>{{ tr('查看更早记录') }}</summary>
      <template v-for="row in earlier" :key="row.key"
        ><p v-if="row.kind === 'group'">{{ row.label }}</p>
        <p v-else>
          {{
            [when(row.entry.created_at), row.event.title, row.event.detail]
              .filter(Boolean)
              .join(' · ')
          }}
        </p></template
      >
      <button v-if="s.timelineCursor" class="text-link" @click="more">
        {{ tr('加载更早记录') }}
      </button>
      <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
    </details>
    <details class="task-earlier" @toggle="toggled">
      <summary>{{ tr('历次方案与决定') }}</summary>
      <p v-if="plansError" role="alert">{{ tr(plansError) }}</p>
      <article v-for="p in plans" :key="p.id" class="task-plan-record">
        <b>{{ tr('方案 v{0} · {1}', [p.plan_version, tr(planStatus[p.status] || p.status)]) }}</b>
        <p>
          {{
            p.proposed_purchase?.quantity
              ? tr('建议补 {0} 件 · {1}', [p.proposed_purchase.quantity, when(p.created_at)])
              : tr('建议本轮不补货 · {0}', [when(p.created_at)])
          }}
        </p>
        <p v-for="a in actions.filter((a) => a.plan_id === p.id)" :key="a.id">
          {{ tr('采购单 {0} 件 · {1}', [a.quantity, tr(actionLabel(a.status, a.channel))]) }}
        </p>
      </article>
      <p v-if="plansLoaded && !plans.length">{{ tr('暂无方案记录。') }}</p>
      <p v-if="plansLoading" class="source-note" role="status">{{ tr('正在读取方案…') }}</p>
      <button
        v-if="plansCursor || plansError"
        class="text-link"
        :disabled="plansLoading"
        @click="loadPlans"
      >
        {{ tr(plansError ? '重试读取方案' : '加载更早方案') }}
      </button>
    </details>
  </section>
</template>
