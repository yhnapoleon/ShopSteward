import type { Schema } from '~/types/models'
import { api, ApiFailure, query } from '~/utils/api'
import { describeTool, type ToolRecord } from '~/utils/agent'

type PendingMessage = {
  key: string
  content: string
  state: 'sending' | 'failed' | 'accepted'
  messageId?: string
}
type Submission = {
  key: string
  content: string
  conversationId: string
  runId?: string
  interruptId?: string
}

// The page owns synchronization; presentation components can mount/unmount without
// losing drafts or starting another poller. State is invalidated on identity/scope changes.
export function useAgentConversation(owner = false) {
  const shop = useShop()
  const { s: business, mission } = shop
  const s = useState('agent-workspace', () => ({
    scope: '',
    epoch: 0,
    reading: false,
    sending: false,
    controlling: false,
    messages: [] as Schema<'MessageView'>[],
    conversation: null as Schema<'ConversationView'> | null,
    run: null as Schema<'RunView'> | null,
    runs: {} as Record<string, Schema<'RunView'>>,
    chatScrollTop: 0,
    chatFollowing: true,
    input: '',
    error: '',
    syncError: '',
    historyError: '',
    pending: null as PendingMessage | null,
    submission: null as Submission | null,
    createKey: '',
    initialized: false,
    seenTools: [] as string[],
    activity: null as { id: string; target: string; label: string; at: number } | null,
    inspectedRunId: '',
    expandedRuns: {} as Record<string, boolean>,
  })).value
  const scope = computed(() =>
    business.session?.authenticated && mission.value
      ? [
          business.session.principal_id,
          [...business.session.roles].sort().join(','),
          business.storeId,
          mission.value.id,
        ].join(':')
      : '',
  )
  const current = (epoch: number, key: string) =>
    s.epoch === epoch && s.scope === key && scope.value === key
  const active = computed(
    () => !!s.run && ['QUEUED', 'RUNNING', 'WAITING_INPUT'].includes(s.run.status),
  )
  const running = computed(
    () => !!s.run && ['QUEUED', 'RUNNING'].includes(s.run.status) && !s.syncError,
  )
  const enabled = computed(
    () =>
      !!business.session?.agentEnabled &&
      !!scope.value &&
      ['ACTIVE', 'PAUSED'].includes(mission.value?.status || ''),
  )
  const status = computed(() => {
    if (s.syncError) return '连接中断，进度待同步'
    if (s.sending) return '正在发送你的要求'
    if (!s.run) return business.session?.agentEnabled ? '等待你的问题' : 'Agent 暂未启用'
    return {
      QUEUED: '已收到，等待处理',
      RUNNING: '正在处理你的要求',
      WAITING_INPUT: '需要你补充信息',
      SUCCEEDED: '本轮工作已完成',
      FAILED: '本轮未完成',
      CANCELLED: '本轮已停止',
    }[s.run.status]
  })
  const inspected = computed(() => (s.inspectedRunId ? s.runs[s.inspectedRunId] || null : s.run))
  const tools = computed<ToolRecord[]>(() => {
    const seen = new Set<string>()
    return (inspected.value?.tools || []).flatMap((raw: unknown) => {
      if (!raw || typeof raw !== 'object') return []
      const r = raw as Record<string, unknown>
      if (
        typeof r.invocation_id !== 'string' ||
        typeof r.tool !== 'string' ||
        seen.has(r.invocation_id)
      )
        return []
      seen.add(r.invocation_id)
      return [
        {
          tool: r.tool,
          invocation_id: r.invocation_id,
          ok: typeof r.ok === 'boolean' ? r.ok : null,
          references: Array.isArray(r.references) ? r.references : [],
        },
      ]
    })
  })
  async function pullMessages(id: string, epoch: number, key: string) {
    let after = s.messages.length ? Math.max(...s.messages.map((m) => m.seq)) : 0
    while (current(epoch, key)) {
      const page = await api<Schema<'MessageList'>>(
        `/api/v1/conversations/${id}/messages?limit=100&after_seq=${after}`,
      )
      if (!current(epoch, key)) return
      const merged = new Map(s.messages.map((m) => [m.id, m]))
      page.items.forEach((m) => merged.set(m.id, m))
      s.messages = [...merged.values()].sort((a, b) => a.seq - b.seq)
      if (s.pending?.messageId && merged.has(s.pending.messageId)) s.pending = null
      if (page.next_after_seq == null || page.next_after_seq <= after) break
      after = page.next_after_seq
    }
  }
  async function load() {
    if (!scope.value || s.scope !== scope.value || s.reading) return
    const epoch = s.epoch,
      key = s.scope,
      id = mission.value!.id
    s.reading = true
    try {
      let cursor: string | null = null
      let conversation: Schema<'ConversationView'> | undefined
      let first: Schema<'ConversationView'> | undefined
      do {
        const list: Schema<'ConversationList'> = await api(
          `/api/v1/missions/${id}/conversations${query({ limit: 100, after: cursor })}`,
        )
        if (!current(epoch, key)) return
        first ||= list.items[0]
        conversation = list.items.find((c) => c.is_default)
        if (list.next_cursor === cursor) break
        cursor = list.next_cursor
      } while (!conversation && cursor)
      conversation ||= first
      if (!conversation) {
        s.syncError = ''
        s.initialized = true
        return
      }
      if (s.conversation && s.conversation.id !== conversation.id) {
        s.messages = []
        s.run = null
        s.runs = {}
        s.seenTools = []
        s.initialized = false
      }
      s.conversation = conversation
      await pullMessages(conversation.id, epoch, key)
      if (!current(epoch, key)) return
      const last = s.messages.findLast((m) => m.run_id)
      const rid =
        conversation.active_run_id ||
        (last && last.seq > (s.run?.input_through_seq ?? 0) ? last.run_id : null) ||
        s.run?.id ||
        last?.run_id
      if (rid) {
        const next = await api<Schema<'RunView'>>('/api/v1/agent-runs/' + rid)
        if (!current(epoch, key)) return
        const previous = s.run
        const fresh = (next.tools || []).filter(
          (t: any) =>
            typeof t.invocation_id === 'string' &&
            !s.seenTools.includes(next.id + ':' + t.invocation_id),
        )
        for (const t of fresh) s.seenTools.push(next.id + ':' + t.invocation_id)
        if (s.initialized) {
          const t = fresh.findLast((t: any) => t.ok === true && describeTool(String(t.tool)).target)
          if (t)
            s.activity = {
              id: next.id + ':' + t.invocation_id,
              target: describeTool(String(t.tool)).target!,
              label: describeTool(String(t.tool)).done,
              at: Date.now(),
            }
        }
        s.run = next
        s.runs[next.id] = next
        const terminal = ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(next.status)
        if (terminal && (!previous || previous.id !== next.id || previous.status !== next.status)) {
          await pullMessages(conversation.id, epoch, key)
          // A failed/cancelled run may already have committed a tool mutation.
          if (current(epoch, key)) await shop.refresh(true)
        } else if (
          s.initialized &&
          fresh.some((t: any) => t.ok && ['revise_plan', 'request_check'].includes(t.tool))
        ) {
          await shop.refresh(true)
        }
      }
      if (current(epoch, key)) {
        s.syncError = ''
        s.initialized = true
      }
    } catch (e) {
      if (current(epoch, key)) s.syncError = (e as Error).message
    } finally {
      if (current(epoch, key)) s.reading = false
    }
  }
  async function send() {
    const content = s.submission?.content || s.input.trim()
    if (
      !content ||
      !enabled.value ||
      s.sending ||
      (active.value && s.run?.status !== 'WAITING_INPUT' && !s.submission)
    )
      return
    const epoch = s.epoch,
      key = s.scope,
      missionId = mission.value!.id
    s.sending = true
    s.error = ''
    try {
      if (!s.conversation) {
        s.createKey ||= crypto.randomUUID()
        const c = await api<Schema<'ConversationView'>>(
          `/api/v1/missions/${missionId}/conversations`,
          'POST',
          { is_default: true, title: '活动备货' },
          s.createKey,
        )
        if (!current(epoch, key)) return
        s.conversation = c
        s.createKey = ''
      }
      s.submission ||= {
        key: crypto.randomUUID(),
        content,
        conversationId: s.conversation.id,
        ...(s.run?.status === 'WAITING_INPUT'
          ? { runId: s.run.id, interruptId: s.run.interrupt_id || undefined }
          : {}),
      }
      const request = s.submission
      s.pending = { key: request.key, content: request.content, state: 'sending' }
      const result = request.runId
        ? await api<Schema<'ResumeAccepted'>>(
            `/api/v1/agent-runs/${request.runId}/resume`,
            'POST',
            { content: request.content, interrupt_id: request.interruptId },
            request.key,
          )
        : await api<Schema<'MessageAccepted'>>(
            `/api/v1/conversations/${request.conversationId}/messages`,
            'POST',
            { content: request.content },
            request.key,
          )
      if (!current(epoch, key)) return
      s.submission = null
      s.input = ''
      s.pending = result.message_id
        ? {
            key: request.key,
            content: request.content,
            state: 'accepted',
            messageId: result.message_id,
          }
        : null
      s.inspectedRunId = ''
      const run = await api<Schema<'RunView'>>('/api/v1/agent-runs/' + result.agent_run_id)
      if (!current(epoch, key)) return
      s.run = run
      s.runs[run.id] = run
      await load()
    } catch (e) {
      if (current(epoch, key)) {
        s.error = (e as Error).message
        if (s.pending && s.pending.state !== 'accepted') s.pending.state = 'failed'
        if (e instanceof ApiFailure && e.status >= 400 && e.status < 500) {
          s.submission = null
          s.pending = null
        }
      }
    } finally {
      if (current(epoch, key)) s.sending = false
    }
  }
  async function cancel() {
    if (!s.run || !active.value || s.controlling) return
    const epoch = s.epoch,
      key = s.scope,
      runId = s.run.id
    s.controlling = true
    s.error = ''
    try {
      const run = await api<Schema<'RunView'>>(`/api/v1/agent-runs/${runId}/cancel`, 'POST', {})
      if (!current(epoch, key)) return
      s.run = run
      s.runs[run.id] = run
      await shop.refresh(true)
      if (current(epoch, key)) await load()
    } catch (e) {
      if (current(epoch, key)) s.error = (e as Error).message
    } finally {
      if (current(epoch, key)) s.controlling = false
    }
  }
  async function toggleFollowup() {
    if (!s.conversation || s.controlling) return
    const epoch = s.epoch,
      key = s.scope,
      c = s.conversation
    s.controlling = true
    s.error = ''
    try {
      const next = await api<Schema<'ConversationView'>>(
        `/api/v1/conversations/${c.id}/followup`,
        'PATCH',
        {
          enabled: !c.followup_enabled,
          interval_seconds: 300,
          expected_version: c.followup_version,
        },
      )
      if (current(epoch, key)) s.conversation = next
    } catch (e) {
      if (current(epoch, key)) s.error = (e as Error).message
    } finally {
      if (current(epoch, key)) s.controlling = false
    }
  }
  async function inspectRun(id: string) {
    s.inspectedRunId = id
    s.historyError = ''
    if (!id || s.runs[id]) return
    const epoch = s.epoch,
      key = s.scope
    try {
      const run = await api<Schema<'RunView'>>('/api/v1/agent-runs/' + id)
      if (current(epoch, key)) s.runs[id] = run
    } catch (e) {
      if (current(epoch, key)) s.historyError = (e as Error).message
    }
  }
  if (owner) {
    watch(
      scope,
      (key) => {
        s.epoch++
        s.scope = key
        s.reading = false
        s.sending = false
        s.controlling = false
        s.messages = []
        s.conversation = null
        s.run = null
        s.runs = {}
        s.input = ''
        s.error = ''
        s.syncError = ''
        s.historyError = ''
        s.chatScrollTop = 0
        s.chatFollowing = true
        s.pending = null
        s.submission = null
        s.createKey = ''
        s.initialized = false
        s.seenTools = []
        s.activity = null
        s.inspectedRunId = ''
        s.expandedRuns = {}
        if (key) void load()
      },
      { immediate: true, flush: 'sync' },
    )
    let timer: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    async function tick() {
      await load()
      if (!stopped) timer = setTimeout(tick, document.hidden ? 20000 : active.value ? 2500 : 5000)
    }
    const visible = () => {
      if (!document.hidden) void load()
    }
    onMounted(() => {
      void tick()
      document.addEventListener('visibilitychange', visible)
    })
    onUnmounted(() => {
      stopped = true
      clearTimeout(timer)
      s.epoch++
      document.removeEventListener('visibilitychange', visible)
    })
  }
  return {
    s,
    scope,
    active,
    running,
    enabled,
    status,
    inspected,
    tools,
    load,
    send,
    cancel,
    toggleFollowup,
    inspectRun,
  }
}
