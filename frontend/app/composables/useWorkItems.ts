import type { Schema } from '~/types/models'
import { api, ApiFailure, query } from '~/utils/api'

type Submission = { path: string; body: Record<string, unknown>; key: string }
export function useWorkItems(owner = false) {
  const shop = useShop()
  const s = useState('work-items', () => ({
    items: [] as Schema<'WorkView'>[],
    detail: null as Schema<'WorkDetail'> | null,
    cursor: null as string | null,
    input: '',
    error: '',
    syncError: '',
    listError: '',
    busy: false,
    available: false,
    accessRevoked: false,
    processorAvailable: false,
    listing: false,
    pages: 1,
    scope: '',
    epoch: 0,
    selected: '',
    pending: null as Submission | null,
  })).value
  const scope = computed(() =>
    shop.s.session?.authenticated && shop.s.storeId
      ? [
          shop.s.session.principal_id,
          [...shop.s.session.roles].sort().join(','),
          shop.s.storeId,
        ].join(':')
      : '',
  )
  const storageKey = () => 'ss.work.pending:' + s.scope
  const current = (epoch: number) => epoch === s.epoch && s.scope === scope.value
  function apply(d: Schema<'WorkDetail'>, requestedId?: string) {
    s.detail = d
    s.selected = d.item.id
    s.items = [
      d.item,
      ...s.items.filter(
        (i) =>
          (requestedId === d.item.id || i.id !== requestedId) &&
          i.id !== d.item.id &&
          (!d.item.mission_id || i.mission_id !== d.item.mission_id),
      ),
    ]
  }
  function revoke() {
    s.accessRevoked = true
    s.busy = false
    s.epoch++
    s.detail = null
    s.items = []
    s.input = ''
    s.pending = null
    s.available = false
    s.syncError = '当前身份的事项访问已失效，请重新连接。'
  }
  async function list(more = false) {
    if (!scope.value || !shop.s.session?.workIntake || s.listing || s.accessRevoked) return
    const epoch = s.epoch
    s.listing = true
    try {
      let cursor: string | null = null
      const items: Schema<'WorkView'>[] = []
      const count = s.pages + (more ? 1 : 0)
      for (let i = 0; i < count; i++) {
        const page: Schema<'WorkList'> = await api(
          '/api/v1/work-items' + query({ store_id: shop.s.storeId, limit: 30, cursor }),
        )
        if (!current(epoch)) return
        items.push(...page.items)
        cursor = page.next_cursor
        s.processorAvailable = page.processor_available
        if (!cursor) break
      }
      s.listError = ''
      s.items = items.map((item) =>
        s.detail?.item.id === item.id && s.detail.item.version > item.version
          ? s.detail.item
          : item,
      )
      s.cursor = cursor
      s.available = true
      s.pages = count
    } catch (e) {
      if (!current(epoch)) return
      if (e instanceof ApiFailure && [401, 403].includes(e.status)) revoke()
      else s.listError = (e as Error).message
    } finally {
      s.listing = false
      if (!current(epoch) && scope.value && !s.accessRevoked) void list()
    }
  }
  async function load(id = s.selected) {
    if (!id || s.accessRevoked) return
    const epoch = s.epoch
    const selection = s.selected
    try {
      const d = await api<Schema<'WorkDetail'>>('/api/v1/work-items/' + id)
      if (!current(epoch) || s.selected !== selection) return
      if (s.detail?.item.id === d.item.id && s.detail.item.version > d.item.version) return
      apply(d, id)
      s.syncError = ''
    } catch (e) {
      if (!current(epoch) || s.selected !== selection) return
      if (e instanceof ApiFailure && [401, 403].includes(e.status)) revoke()
      else if (e instanceof ApiFailure && e.status === 404) {
        s.detail = null
        s.selected = ''
        s.syncError = '无法读取这件事，请返回今日选择可见事项。'
      } else s.syncError = (e as Error).message
    }
  }
  async function select(id: string) {
    s.selected = id
    s.detail = null
    s.error = ''
    s.syncError = ''
    s.input = ''
    await load(id)
  }
  async function submit(request: Submission) {
    if (s.busy || s.accessRevoked) return
    if (s.pending && (s.pending.key !== request.key || s.pending.path !== request.path)) {
      s.error = '上次提交的结果尚未确认，请先查询并重试原提交。'
      return
    }
    const epoch = s.epoch
    const selection = s.selected
    s.error = ''
    s.busy = true
    s.pending = request
    // Persist before transmitting: a refresh can replay exactly the same request.
    try {
      sessionStorage.setItem(storageKey(), JSON.stringify(request))
      const d = await api<Schema<'WorkDetail'>>(request.path, 'POST', request.body, request.key)
      if (!current(epoch)) return
      sessionStorage.removeItem(storageKey())
      s.pending = null
      if (selection !== s.selected) {
        await list()
        return
      }
      s.input = ''
      apply(d, request.path.match(/^\/api\/v1\/work-items\/([^/]+)/)?.[1])
      await list()
      return d
    } catch (e) {
      if (current(epoch)) {
        s.error = (e as Error).message
        if (e instanceof ApiFailure && e.status >= 400 && e.status < 500) {
          sessionStorage.removeItem(storageKey())
          s.pending = null
          if ([401, 403, 404].includes(e.status)) revoke()
          else await load()
        }
      }
    } finally {
      if (current(epoch)) s.busy = false
    }
  }
  const send = (newItem = false) => {
    if (s.pending) return submit(s.pending)
    if (!s.input.trim()) return
    return submit({
      path: newItem ? '/api/v1/work-items' : '/api/v1/work-items/' + s.selected + '/messages',
      body: newItem
        ? { store_id: shop.s.storeId, content: s.input.trim() }
        : { content: s.input.trim() },
      key: crypto.randomUUID(),
    })
  }
  const control = (operation: 'cancel' | 'retry') =>
    s.detail &&
    submit({
      path: '/api/v1/work-items/' + s.selected + '/control',
      body: { operation, expected_version: s.detail.item.version },
      key: crypto.randomUUID(),
    })
  const acceptMission = () =>
    s.detail &&
    submit({
      path: '/api/v1/work-items/' + s.selected + '/mission',
      body: { expected_version: s.detail.item.version },
      key: crypto.randomUUID(),
    })
  const fromMission = (id: string) =>
    submit({ path: '/api/v1/missions/' + id + '/work-item', body: {}, key: crypto.randomUUID() })
  function label(item: Schema<'WorkView'>) {
    if (s.syncError && s.detail?.item.id === item.id) return '进度待同步'
    if (
      item.status === 'PROCESSING' &&
      item.processing_expires_at &&
      Date.parse(item.processing_expires_at) <= Date.now()
    )
      return '处理中断，等待恢复'
    if (item.mission && ['RESULT_READY', 'COMPLETED'].includes(item.status))
      return {
        ACTIVE: '持续跟进中',
        PAUSED: '备货跟进已暂停',
        COMPLETED: '备货委托已结束',
        CANCELLED: '备货委托已取消',
      }[item.mission.status]
    return {
      RECEIVED: '已收到',
      PROCESSING: '正在处理',
      WAITING_INPUT: '需要你补充',
      RESULT_READY: '结果已出',
      BLOCKED: '需要处理',
      COMPLETED: '本次事项已完成',
      CANCELLED: '本轮处理已停止',
    }[item.status]
  }
  let timer: ReturnType<typeof setInterval> | undefined
  if (owner) {
    watch(
      scope,
      () => {
        s.accessRevoked = false
        s.pages = 1
        s.processorAvailable = false
        s.epoch++
        s.scope = scope.value
        s.items = []
        s.detail = null
        s.selected = ''
        s.pending = null
        s.input = ''
        s.error = ''
        s.syncError = ''
        s.listError = ''
        s.busy = false
        s.available = false
        s.cursor = null
        if (import.meta.client && s.scope) {
          try {
            s.pending = JSON.parse(sessionStorage.getItem(storageKey()) || 'null')
          } catch {}
        }
        void list()
      },
      { immediate: true },
    )
    // Reconnecting the same identity is an explicit opportunity to revalidate access.
    watch(
      () => shop.s.session,
      (session) => {
        if (s.accessRevoked && session?.authenticated && s.scope === scope.value) {
          s.accessRevoked = false
          s.syncError = ''
          s.listError = ''
          s.epoch++
          void list()
          if (s.selected) void load()
        }
      },
    )
    watch(
      () => shop.s.session?.workIntake,
      () => void list(),
    )
    onMounted(() => {
      timer = setInterval(() => {
        if (scope.value && shop.s.session?.workIntake && !s.busy && !s.accessRevoked) {
          void list()
          if (s.selected) void load()
        }
      }, 2500)
    })
    onUnmounted(() => clearInterval(timer))
  }
  return { s, scope, list, load, select, submit, send, control, acceptMission, fromMission, label }
}
