<script setup lang="ts">
import { locale, t as tr } from '~/i18n'
import { describeTool } from '~/utils/agent'
import type { MemoryItem, MemoryKind } from '~/composables/useAgentKnowledge'

// The memory drawer (workspace redesign §8). The page mounts one. It owns the store-scoped cache
// and notices memories the Agent forms while the page is open (useAgentKnowledge owner).
const memory = useAgentKnowledge(true)
const { s, open, scopes, loaded, empty, readOnly, available } = memory
const dialog = ref<HTMLDialogElement>()
const uid = useId()
const editing = ref('')
const draft = ref('')
const confirming = ref('')
const problem = ref<{ id: string; text: string } | null>(null)
const done = ref('')
const busy = computed(() => !!s.saving)

const kinds = [
  {
    kind: 'USER',
    title: '关于你',
    hint: '你的通用偏好，例如现金底线',
    none: '还没有关于你的偏好。',
  },
  { kind: 'NOTES', title: '经营笔记', hint: '店铺相对稳定的背景', none: '还没有经营笔记。' },
  {
    kind: 'SKILL',
    title: '技能',
    hint: '做某类事项的固定做法，例如报价整理顺序',
    none: '还没有形成技能。',
  },
] as const
const tasks: Record<string, string> = { replenishment: '备货委托', quotation: '报价整理' }
const taskOrder = (type: string) => (type in tasks ? Object.keys(tasks).indexOf(type) : 99)
// Tools a skill may depend on that the Agent progress catalog does not describe.
const otherTools: Record<string, string> = {
  process_quotation: '整理报价',
}
const toolName = (name: string) => {
  const known = describeTool(name)
  return known.kind === '工具调用' ? otherTools[name] || '其他工具' : known.title
}
/** A skill's title is its first sentence; a structured rule is said in words, never as JSON. */
function skillText(content: string) {
  const text = content.trim()
  if (text.startsWith('{')) {
    try {
      const value = JSON.parse(text)
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        if (
          value.schema === 'quotation-sort-v1' &&
          ['unit_price', 'source'].includes(value.sort_by)
        )
          return {
            title:
              value.sort_by === 'unit_price' ? '整理报价时按单件价排序' : '整理报价时按来源排序',
            system: true,
            body: '',
            raw: '',
          }
        return { title: '一条系统规则', system: true, body: '', raw: text }
      }
    } catch {
      // Not structured: read it as written.
    }
  }
  const end = /[。！？!?\n]|\.(?=\s|$)/.exec(text)
  if (!end || end.index === 0) return { title: text, system: false, body: '', raw: '' }
  return {
    title: text.slice(0, end.index).trim(),
    system: false,
    body: text.slice(end.index + end[0].length).trim(),
    raw: '',
  }
}
function row(kind: MemoryKind, taskType: string, item: MemoryItem) {
  if (kind !== 'SKILL') return { item, title: '', system: false, body: '', raw: '', meta: '' }
  const task = tr(tasks[taskType] || '其他事项')
  // Tool titles may themselves contain "、", so tools are separated one level up.
  const tools = [...new Set(item.tools.map(toolName))]
    .map((name) => tr(name))
    .join(locale.value === 'en' ? '; ' : '；')
  return {
    item,
    ...skillText(item.content),
    meta: tools ? tr('适用：{0} · 依赖工具：{1}', [task, tools]) : tr('适用：{0}', [task]),
  }
}
// Three sections in a fixed order; skills are grouped by the kind of work they apply to.
const sections = computed(() =>
  kinds.map((k) => {
    const own = scopes.value.filter((scope) => scope.kind === k.kind)
    const groups = own
      .map((scope) => ({
        key: k.kind + ':' + scope.taskType,
        taskType: scope.taskType,
        label: k.kind === 'SKILL' ? tr(tasks[scope.taskType] || '其他事项') : '',
        version: scope.version,
        rows: scope.items.map((item) => row(k.kind, scope.taskType, item)),
      }))
      .filter((group) => group.rows.length)
      .sort(
        (a, b) =>
          taskOrder(a.taskType) - taskOrder(b.taskType) || a.taskType.localeCompare(b.taskType),
      )
    return {
      ...k,
      // Skills show a version per group; the other two have one scope each.
      version: k.kind === 'SKILL' ? null : (own[0]?.version ?? null),
      groups,
      count: groups.reduce((n, group) => n + group.rows.length, 0),
    }
  }),
)

function focusAction(id: string) {
  void nextTick(() => {
    const action = id
      ? dialog.value?.querySelector<HTMLElement>(`[data-memory-action="${CSS.escape(id)}"]`)
      : null
    ;(action && !action.matches(':disabled')
      ? action
      : document.getElementById(uid + '-title')
    )?.focus()
  })
}
async function startEdit(item: MemoryItem) {
  problem.value = null
  confirming.value = ''
  editing.value = item.id
  draft.value = item.content
  await nextTick()
  const area = document.getElementById(uid + '-draft') as HTMLTextAreaElement | null
  area?.focus()
  area?.setSelectionRange(area.value.length, area.value.length)
}
function stopEdit() {
  const id = editing.value
  editing.value = ''
  draft.value = ''
  if (id) focusAction(id)
}
function askRemove(item: MemoryItem) {
  problem.value = null
  editing.value = ''
  confirming.value = item.id
  void nextTick(() => document.getElementById(uid + '-keep')?.focus())
}
function keep() {
  const id = confirming.value
  confirming.value = ''
  if (id) focusAction(id)
}
let doneTimer: ReturnType<typeof setTimeout> | undefined
function announce(text: string) {
  done.value = text
  clearTimeout(doneTimer)
  doneTimer = setTimeout(() => (done.value = ''), 4000)
}
async function correct(kind: MemoryKind, item: MemoryItem) {
  const content = draft.value.trim()
  if (!content || content === item.content.trim()) return
  problem.value = null
  const failure = await memory.edit({ kind, operation: 'replace', entry_id: item.id, content })
  if (failure) {
    // Refused because the Agent is off: the read-only notice at the top already says so.
    if (!readOnly.value) problem.value = { id: item.id, text: failure }
    return
  }
  editing.value = ''
  draft.value = ''
  announce('已更新这条记忆。')
  focusAction(item.id)
}
async function remove(kind: MemoryKind, taskType: string, item: MemoryItem) {
  problem.value = null
  const failure = await memory.edit({
    kind,
    task_type: taskType,
    operation: 'remove',
    entry_id: item.id,
  })
  confirming.value = ''
  if (failure) {
    if (!readOnly.value) problem.value = { id: item.id, text: failure }
    focusAction(item.id)
    return
  }
  announce(kind === 'SKILL' ? '已停用这项技能。' : '已删除这条记忆。')
  focusAction('')
}

// Drawer motion (§12): slides in from the right on the drawer curve within 300ms and leaves
// faster. Opened or closed from the keyboard it appears and disappears without motion.
let origin: HTMLElement | null = null
let leaving: ReturnType<typeof setTimeout> | undefined
let keyboard = false
const fromPointer = () => (keyboard = false)
const fromKeyboard = (event: KeyboardEvent) => {
  if (!['Shift', 'Control', 'Alt', 'Meta'].includes(event.key)) keyboard = true
}
function restore() {
  const target = origin
  origin = null
  if (target?.isConnected && target.getClientRects().length) target.focus({ preventScroll: true })
}
function finish() {
  clearTimeout(leaving)
  const el = dialog.value
  if (!el || open.value) return
  if (el.open) el.close()
  delete el.dataset.state
  restore()
}
function present() {
  const el = dialog.value
  if (!el) return
  clearTimeout(leaving)
  memory.acknowledge()
  void memory.load()
  // Asked to open again while leaving: turn the same transition around.
  if (el.open) {
    memory.takeOpener()
    el.dataset.state = 'open'
    return
  }
  origin = memory.takeOpener()
  problem.value = null
  done.value = ''
  el.dataset.state = keyboard ? 'open' : 'entering'
  el.showModal()
  if (el.dataset.state === 'entering') {
    // Commit the off-screen position, then slide in from it.
    void el.offsetWidth
    el.dataset.state = 'open'
  }
}
function dismiss() {
  const el = dialog.value
  editing.value = ''
  draft.value = ''
  confirming.value = ''
  if (!el?.open) return restore()
  if (keyboard) return finish()
  el.dataset.state = 'closing'
  clearTimeout(leaving)
  leaving = setTimeout(finish, 220)
}
watch(open, (value) => (value ? present() : dismiss()))
onMounted(() => {
  document.addEventListener('pointerdown', fromPointer, true)
  document.addEventListener('keydown', fromKeyboard, true)
  if (open.value) present()
})
onUnmounted(() => {
  document.removeEventListener('pointerdown', fromPointer, true)
  document.removeEventListener('keydown', fromKeyboard, true)
  clearTimeout(leaving)
  clearTimeout(doneTimer)
})
// Escape steps back one level: out of an edit or a confirmation first, then out of the drawer.
function onCancel(event: Event) {
  event.preventDefault()
  if (editing.value) return stopEdit()
  if (confirming.value) return keep()
  memory.hide()
}
// The browser may close the dialog itself (a repeated Escape); keep the shared state in step.
function onClose() {
  if (open.value) memory.hide()
}
function onBackdrop(event: MouseEvent) {
  const el = dialog.value
  if (!el || event.target !== el) return
  const r = el.getBoundingClientRect()
  if (
    event.clientX < r.left ||
    event.clientX > r.right ||
    event.clientY < r.top ||
    event.clientY > r.bottom
  )
    memory.hide()
}
</script>
<template>
  <dialog
    ref="dialog"
    class="memory-drawer"
    :aria-labelledby="uid + '-title'"
    @cancel="onCancel"
    @close="onClose"
    @click="onBackdrop"
  >
    <header class="memory-head">
      <div>
        <h2 :id="uid + '-title'" tabindex="-1">{{ tr('系统记住了什么') }}</h2>
        <p>{{ tr('Agent 跨对话记住的内容，只用于你在当前店铺的对话。') }}</p>
      </div>
      <button class="icon-btn" :aria-label="tr('关闭记忆面板')" @click="memory.hide()">
        <AppIcon name="x" />
      </button>
    </header>
    <div class="memory-body">
      <p v-if="readOnly && available" class="notice memory-readonly">
        <AppIcon name="lock-keyhole" /><span>{{
          tr('修改记忆需要启用 Agent。现在可以查看，纠正、删除与停用暂不可用。')
        }}</span>
      </p>
      <p class="memory-done" role="status">{{ done ? tr(done) : '' }}</p>
      <p v-if="!available" class="memory-loading">
        {{ tr('连接后端身份并选择店铺后，可以在这里查看记忆。') }}
      </p>
      <p v-else-if="s.error" class="notice amber" role="alert">
        {{ tr('暂时读不到记忆：{0}', [tr(s.error)]) }}
        <button class="text-link" :disabled="s.loading" @click="memory.load()">
          {{ tr('重试读取') }}
        </button>
      </p>
      <p v-if="available && !loaded && !s.error" class="memory-loading" role="status">
        {{ tr('正在读取记忆…') }}
      </p>
      <section v-else-if="loaded && empty" class="memory-empty" :aria-labelledby="uid + '-empty'">
        <span class="settings-symbol"><AppIcon name="sparkles" /></span>
        <h3 :id="uid + '-empty'">{{ tr('还没有记住任何内容') }}</h3>
        <p>
          {{ tr('在对话里说“以后现金至少留 500”，Agent 会记下来；报价纠正会形成整理规则。') }}
        </p>
        <dl class="memory-kinds">
          <div v-for="k in kinds" :key="k.kind">
            <dt>{{ tr(k.title) }}</dt>
            <dd>{{ tr(k.hint) }}</dd>
          </div>
        </dl>
        <p class="source-note">{{ tr('记下的内容会出现在这里，可以纠正、删除或停用。') }}</p>
      </section>
      <template v-else-if="loaded">
        <section
          v-for="section in sections"
          :key="section.kind"
          class="memory-section"
          :aria-labelledby="uid + '-' + section.kind"
        >
          <div class="memory-section-head">
            <h3 :id="uid + '-' + section.kind">{{ tr(section.title) }}</h3>
            <span
              v-if="section.version !== null"
              class="memory-version"
              :title="tr('版本 {0}', [section.version])"
              >v{{ section.version }}</span
            >
          </div>
          <p class="memory-hint">{{ tr(section.hint) }}</p>
          <p v-if="!section.count" class="memory-none">{{ tr(section.none) }}</p>
          <div v-for="group in section.groups" :key="group.key" class="memory-group">
            <div v-if="group.label" class="memory-group-head">
              <h4>{{ group.label }}</h4>
              <span class="memory-version" :title="tr('版本 {0}', [group.version])"
                >v{{ group.version }}</span
              >
            </div>
            <ul class="memory-list">
              <li v-for="entry in group.rows" :key="entry.item.id" class="memory-item">
                <template v-if="editing === entry.item.id">
                  <label class="sr-only" :for="uid + '-draft'">{{ tr('纠正这条记忆') }}</label>
                  <textarea
                    :id="uid + '-draft'"
                    v-model="draft"
                    class="memory-draft"
                    rows="3"
                    maxlength="6000"
                    :disabled="busy"
                  />
                  <div class="memory-actions">
                    <button
                      class="primary memory-save"
                      :disabled="
                        busy ||
                        readOnly ||
                        !draft.trim() ||
                        draft.trim() === entry.item.content.trim()
                      "
                      @click="correct(section.kind, entry.item)"
                    >
                      {{ tr(s.saving === entry.item.id ? '正在保存…' : '保存纠正') }}
                    </button>
                    <button class="text-link" :disabled="busy" @click="stopEdit">
                      {{ tr('取消') }}
                    </button>
                  </div>
                </template>
                <template v-else>
                  <template v-if="section.kind === 'SKILL'">
                    <strong class="memory-title">{{
                      entry.system ? tr(entry.title) : entry.title
                    }}</strong>
                    <p v-if="entry.body" class="memory-text">{{ entry.body }}</p>
                    <p class="memory-meta">{{ entry.meta }}</p>
                    <details v-if="entry.raw" class="memory-raw">
                      <summary>{{ tr('查看原始内容') }}</summary>
                      <code>{{ entry.raw }}</code>
                    </details>
                  </template>
                  <p v-else class="memory-text">{{ entry.item.content }}</p>
                  <div
                    v-if="confirming === entry.item.id"
                    class="memory-confirm"
                    role="group"
                    :aria-label="tr(section.kind === 'SKILL' ? '确认是否停用' : '确认是否删除')"
                  >
                    <p>
                      {{
                        tr(
                          section.kind === 'SKILL'
                            ? '停用后 Agent 不再沿用这项做法。'
                            : '删除后 Agent 不再参考这条。',
                        )
                      }}
                    </p>
                    <div class="memory-actions">
                      <button :id="uid + '-keep'" class="text-link" :disabled="busy" @click="keep">
                        {{ tr('保留') }}</button
                      ><button
                        class="secondary memory-danger"
                        :disabled="busy || readOnly"
                        @click="remove(section.kind, group.taskType, entry.item)"
                      >
                        {{
                          tr(
                            s.saving === entry.item.id
                              ? '正在保存…'
                              : section.kind === 'SKILL'
                                ? '确认停用'
                                : '确认删除',
                          )
                        }}
                      </button>
                    </div>
                  </div>
                  <div v-else class="memory-actions">
                    <button
                      v-if="section.kind === 'SKILL'"
                      class="text-link"
                      :data-memory-action="entry.item.id"
                      :disabled="busy || readOnly"
                      @click="askRemove(entry.item)"
                    >
                      {{ tr('停用') }}
                    </button>
                    <template v-else>
                      <button
                        class="text-link"
                        :data-memory-action="entry.item.id"
                        :disabled="busy || readOnly"
                        @click="startEdit(entry.item)"
                      >
                        {{ tr('纠正') }}</button
                      ><button
                        class="text-link"
                        :disabled="busy || readOnly"
                        @click="askRemove(entry.item)"
                      >
                        {{ tr('删除') }}
                      </button>
                    </template>
                  </div>
                </template>
                <p
                  v-if="problem && problem.id === entry.item.id"
                  class="notice amber memory-problem"
                  role="alert"
                >
                  {{ tr(problem.text) }}
                </p>
              </li>
            </ul>
          </div>
        </section>
        <p class="source-note memory-foot">
          {{ tr('后端暂未记录每条记忆的时间与来源，这里只显示每类记忆的版本。') }}
        </p>
      </template>
    </div>
  </dialog>
</template>
