import type { Schema } from '~/types/models'
import { api, ApiFailure } from '~/utils/api'
import { runTools } from '~/utils/agent-progress'

// Agent memory for the current identity and store (workspace redesign §8): what the Agent keeps
// across conversations, read from and written to /agent-knowledge. The backend records no time
// or source per entry, so nothing here shows or invents one.

export type MemoryKind = Schema<'KnowledgeView'>['kind']
export type MemoryItem = { id: string; content: string; tools: string[] }
export type MemoryScope = {
  kind: MemoryKind
  taskType: string
  version: number
  items: MemoryItem[]
}
export type MemoryChange = {
  kind: MemoryKind
  task_type?: string
  operation: Schema<'KnowledgeChange'>['operation']
  entry_id?: string
  content?: string
  required_tools?: string[]
}

// Messages are Chinese source text; the panel translates them when it shows them.
const reasons: Record<string, string> = {
  VERSION_CONFLICT: '这部分记忆刚刚有了更新，已载入最新内容，请核对后再改。',
  MEMORY_ENTRY_NOT_FOUND: '这条记忆已经不存在，列表已刷新。',
  EMPTY_KNOWLEDGE: '内容不能为空。',
  MEMORY_CHANGE_REJECTED: '这条内容没有通过记忆规则检查，未保存。',
  SKILL_BUDGET_EXCEEDED: '这类技能的内容超出容量，未保存。',
  BACKEND_UNAVAILABLE: '没有取得保存结果，已重新读取；请核对后再决定是否重试。',
  CONNECTION_ERROR: '没有取得保存结果，已重新读取；请核对后再决定是否重试。',
}
// After these the stored memory is newer than the page, or unknown: read it again.
const reread = [
  'VERSION_CONFLICT',
  'MEMORY_ENTRY_NOT_FOUND',
  'BACKEND_UNAVAILABLE',
  'CONNECTION_ERROR',
]
const writeDisabled = '修改记忆需要启用 Agent。'

// The control that opened the panel. Focus returns to it on close; Safari does not focus a
// clicked button, so openers pass themselves instead of relying on document.activeElement.
let opener: HTMLElement | null = null

/** Entries arrive as loose objects; keep only the fields the panel can show. */
function readItems(raw: Schema<'KnowledgeView'>['entries']): MemoryItem[] {
  return (raw || []).flatMap((entry) =>
    typeof entry.id === 'string' && typeof entry.content === 'string'
      ? [
          {
            id: entry.id,
            content: entry.content,
            tools: Array.isArray(entry.required_tools)
              ? entry.required_tools.filter((tool): tool is string => typeof tool === 'string')
              : [],
          },
        ]
      : [],
  )
}

export function useAgentKnowledge(owner = false) {
  const shop = useShop()
  const s = useState('agent-knowledge', () => ({
    key: '',
    scopes: [] as MemoryScope[],
    loaded: false,
    loading: false,
    error: '',
    saving: '',
    writeBlocked: false,
    learned: 0,
    receipt: { scope: '', count: 0 },
    request: 0,
  })).value
  /** The drawer's open state, shared by the header entry, settings and conversation receipts. */
  const open = useState('memory-panel', () => false)
  /** Memory belongs to one identity in one store. */
  const key = computed(() =>
    shop.s.session?.authenticated && shop.s.storeId
      ? shop.s.session.principal_id + ':' + shop.s.storeId
      : '',
  )
  /** An identity and a store are known, so there is memory to read. */
  const available = computed(() => !!key.value)
  const current = computed(() => available.value && s.key === key.value)
  const scopes = computed(() => (current.value ? s.scopes : []))
  const loaded = computed(() => current.value && s.loaded)
  const empty = computed(() => !scopes.value.some((scope) => scope.items.length))
  const readOnly = computed(() => !shop.s.session?.agentEnabled || s.writeBlocked)
  /** Memories formed since the panel was last opened (the header dot). */
  const learned = computed(() => s.learned)

  async function load() {
    const k = key.value,
      store = shop.s.storeId
    if (!k) return
    const sequence = ++s.request
    s.loading = true
    try {
      const list = await api<Schema<'KnowledgeList'>>(`/api/v1/stores/${store}/agent-knowledge`)
      if (sequence !== s.request || key.value !== k) return
      s.scopes = (list.items || []).map((scope) => ({
        kind: scope.kind,
        taskType: scope.task_type || '',
        version: scope.version,
        items: readItems(scope.entries),
      }))
      s.key = k
      s.loaded = true
      s.error = ''
    } catch (e) {
      if (sequence === s.request && key.value === k) s.error = (e as Error).message
    } finally {
      if (sequence === s.request) s.loading = false
    }
  }

  /** Write one change against the scope version on screen. Resolves to '' or a reason. */
  async function edit(change: MemoryChange): Promise<string> {
    const k = key.value,
      store = shop.s.storeId
    if (!k || s.saving) return ''
    if (readOnly.value) return writeDisabled
    const skill = change.kind === 'SKILL'
    const taskType = skill ? change.task_type || '' : ''
    const scope = scopes.value.find((x) => x.kind === change.kind && x.taskType === taskType)
    // Only skills carry a task type and tool requirements; a scope not yet created is version 0.
    const body: Record<string, unknown> = {
      kind: change.kind,
      expected_version: scope?.version ?? 0,
      operation: change.operation,
    }
    if (change.entry_id) body.entry_id = change.entry_id
    if (change.content !== undefined) body.content = change.content
    if (skill) {
      body.task_type = taskType
      if (change.required_tools) body.required_tools = change.required_tools
    }
    s.saving = change.entry_id || change.operation
    try {
      await api<Schema<'KnowledgeView'>>(
        `/api/v1/stores/${store}/agent-knowledge`,
        'POST',
        body,
        crypto.randomUUID(),
      )
      if (key.value === k) await load()
      return ''
    } catch (e) {
      if (key.value !== k) return ''
      const failure = e instanceof ApiFailure ? e : null
      // The backend runs without an Agent: memory stays readable, writes are refused.
      if (failure && (failure.status === 503 || failure.code === 'AGENT_NOT_CONFIGURED')) {
        s.writeBlocked = true
        return writeDisabled
      }
      if (failure && reread.includes(failure.code)) await load()
      return (failure && reasons[failure.code]) || (e as Error).message
    } finally {
      if (key.value === k) s.saving = ''
    }
  }

  function show(trigger?: EventTarget | null) {
    if (open.value) return
    const active = document.activeElement
    opener =
      trigger instanceof HTMLElement
        ? trigger
        : active instanceof HTMLElement && active !== document.body
          ? active
          : null
    open.value = true
  }
  function hide() {
    open.value = false
  }
  function acknowledge() {
    s.learned = 0
  }
  function takeOpener() {
    const element = opener
    opener = null
    return element
  }

  if (owner) {
    watch(
      key,
      (next) => {
        s.request++
        s.key = next
        s.scopes = []
        s.loaded = false
        s.loading = false
        s.error = ''
        s.saving = ''
        s.writeBlocked = false
        s.learned = 0
        if (next && open.value) void load()
      },
      { immediate: true, flush: 'sync' },
    )
    // A memory the Agent formed while the page is open: a successful memory_edit in the current
    // run, counted once per run and invocation. Whatever is present when watching starts, or
    // arrives while a conversation is still being read for the first time, is history.
    const agent = useAgentConversation()
    const seen = new Set<string>()
    let primed = false
    watch(
      () => {
        const run = agent.s.run
        return run
          ? runTools(run)
              .filter((tool) => tool.tool === 'memory_edit' && tool.ok === true)
              .map((tool) => run.id + ':' + tool.invocation_id)
          : []
      },
      (ids) => {
        const fresh = ids.filter((id) => !seen.has(id))
        fresh.forEach((id) => seen.add(id))
        if (!primed || !agent.s.initialized) {
          primed = true
          return
        }
        if (!fresh.length) return
        s.learned += fresh.length
        s.receipt = {
          scope: agent.s.scope,
          count: (s.receipt.scope === agent.s.scope ? s.receipt.count : 0) + fresh.length,
        }
        void load()
      },
      // Synchronous, so `initialized` is read exactly when the run changes during a load.
      { immediate: true, flush: 'sync' },
    )
  }

  return {
    s,
    open,
    available,
    scopes,
    loaded,
    empty,
    readOnly,
    learned,
    load,
    edit,
    show,
    hide,
    acknowledge,
    takeOpener,
  }
}
