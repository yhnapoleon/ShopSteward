import { api, ApiFailure, query } from '~/utils/api'
import type { RecoveryCase, RecoveryCandidate } from '~/types/recovery'

type Submission = { path: string; body: Record<string, unknown>; key: string; phase: string }

export function useRecoveryCase(missionId: () => string) {
  const shop = useShop()
  const detail = ref<RecoveryCase | null>(null)
  const items = ref<RecoveryCase[]>([])
  const busy = ref(false),
    error = ref(''),
    syncError = ref(''),
    pending = ref<Submission | null>(null)
  const revoked = ref(false)
  const drafting = ref(false)
  let epoch = 0
  const scope = computed(() =>
    [
      shop.s.session?.principal_id || '',
      [...(shop.s.session?.roles || [])].sort().join(','),
      shop.s.storeId,
      missionId(),
    ].join(':'),
  )
  const storageKey = () => 'ss.recovery.pending:' + scope.value
  const current = (n: number, key: string) => n === epoch && key === scope.value
  function apply(value: RecoveryCase) {
    if (value.mission_id !== missionId() || value.store_id !== shop.s.storeId) return
    if (detail.value?.id === value.id && detail.value.current_revision > value.current_revision)
      return
    detail.value = value
    items.value = [value, ...items.value.filter((c) => c.id !== value.id)]
  }
  function accessLost() {
    revoked.value = true
    detail.value = null
    items.value = []
    pending.value = null
    epoch++
    busy.value = false
    error.value = '当前身份无权读取这项恢复事项，请重新连接。'
  }
  async function load(id?: string) {
    if (!missionId() || revoked.value) return
    const n = epoch,
      key = scope.value
    try {
      if (id) {
        const value = await api<RecoveryCase>('/api/v1/operations-cases/' + encodeURIComponent(id))
        if (current(n, key)) {
          drafting.value = false
          apply(value)
        }
      } else {
        const page = await api<{ items: RecoveryCase[] }>(
          '/api/v1/operations-cases' + query({ store_id: shop.s.storeId }),
        )
        if (!current(n, key)) return
        items.value = page.items.filter((c) => c.mission_id === missionId())
        const latest =
          items.value.find((c) => !['CLOSED', 'CANCELLED'].includes(c.status)) || items.value[0]
        if (latest && !drafting.value) apply(latest)
      }
      if (current(n, key)) syncError.value = ''
    } catch (e) {
      if (!current(n, key)) return
      if (e instanceof ApiFailure && [401, 403, 404].includes(e.status)) accessLost()
      else syncError.value = (e as Error).message
    }
  }
  async function submit(request: Submission): Promise<RecoveryCase | undefined> {
    if (busy.value || revoked.value || !shop.hasRole('operator')) return
    if (pending.value && request.key !== pending.value.key) {
      error.value = '原提交结果尚未确认，请先核实并重试原提交。'
      return
    }
    const n = epoch,
      key = scope.value,
      storedKey = storageKey()
    busy.value = true
    error.value = ''
    pending.value = request
    try {
      sessionStorage.setItem(storedKey, JSON.stringify(request))
      const value = await api<RecoveryCase>(request.path, 'POST', request.body, request.key)
      if (!current(n, key)) return
      sessionStorage.removeItem(storedKey)
      pending.value = null
      drafting.value = false
      apply(value)
      return value
    } catch (e) {
      if (!current(n, key)) return
      error.value = (e as Error).message
      if (e instanceof ApiFailure && e.status >= 400 && e.status < 500) {
        sessionStorage.removeItem(storedKey)
        pending.value = null
        if ([401, 403, 404].includes(e.status)) accessLost()
        else if (detail.value) await load(detail.value.id)
      }
    } finally {
      if (current(n, key)) busy.value = false
    }
  }
  const post = (phase: string, path: string, body: Record<string, unknown>) =>
    submit({ phase, path, body, key: crypto.randomUUID() })
  async function analyze(value = detail.value) {
    if (!value) return
    return post('analyze', `/api/v1/operations-cases/${encodeURIComponent(value.id)}/analyze`, {
      expected_revision: value.current_revision,
    })
  }
  async function start(body: Record<string, unknown>) {
    const value = await post('create', '/api/v1/operations-cases', {
      ...body,
      mission_id: missionId(),
    })
    if (value) return analyze(value)
  }
  async function revise(body: Record<string, unknown>) {
    const value = detail.value
    if (!value) return
    const updated = await post(
      'revise',
      `/api/v1/operations-cases/${encodeURIComponent(value.id)}/revise`,
      {
        ...body,
        expected_revision: value.current_revision,
      },
    )
    if (updated) return analyze(updated)
  }
  async function materialize(candidate: RecoveryCandidate) {
    const value = detail.value,
      proposal = value?.proposal
    if (
      !value ||
      !proposal ||
      !candidate.feasible ||
      !candidate.executable ||
      candidate.quantity === 0
    )
      return
    return post(
      'materialize',
      `/api/v1/operations-cases/${encodeURIComponent(value.id)}/materialize`,
      {
        expected_revision: value.current_revision,
        proposal_id: proposal.id,
        candidate_id: candidate.id,
        expected_mission_version: value.current_mission_version,
        expected_state_version: value.current_state_version,
        expected_current_plan_id: value.current_plan_id,
        proposal_hash: proposal.proposal_hash,
      },
    )
  }
  async function control(
    operation: 'adopt_waiting' | 'cancel' | 'refresh' | 'enable_followup' | 'disable_followup',
  ) {
    const value = detail.value
    if (!value) return
    const updated = await post(
      operation === 'refresh' ? 'refresh' : 'control',
      `/api/v1/operations-cases/${encodeURIComponent(value.id)}/control`,
      {
        expected_revision: value.current_revision,
        operation,
      },
    )
    return updated && operation === 'refresh' ? analyze(updated) : updated
  }
  async function retry() {
    const request = pending.value
    if (!request) return
    const value = await submit(request)
    if (value && ['create', 'revise', 'refresh'].includes(request.phase)) return analyze(value)
    return value
  }
  watch(
    scope,
    () => {
      epoch++
      detail.value = null
      items.value = []
      busy.value = false
      pending.value = null
      error.value = ''
      syncError.value = ''
      revoked.value = false
      drafting.value = false
      if (!import.meta.client) return
      try {
        const saved = JSON.parse(sessionStorage.getItem(storageKey()) || 'null')
        if (
          saved &&
          typeof saved.key === 'string' &&
          typeof saved.phase === 'string' &&
          /^\/api\/v1\/operations-cases(?:\/[^/]+\/(?:analyze|revise|materialize|control))?$/.test(
            saved.path,
          ) &&
          saved.body &&
          typeof saved.body === 'object'
        )
          pending.value = saved
      } catch {
        error.value = '无法恢复上次提交记录，请先核对事项状态。'
      }
    },
    { immediate: true },
  )
  onUnmounted(() => {
    epoch++
  })
  function newDraft() {
    if (busy.value || pending.value || revoked.value) return false
    epoch++
    detail.value = null
    drafting.value = true
    error.value = ''
    syncError.value = ''
    return true
  }
  return {
    detail,
    items,
    busy,
    error,
    syncError,
    pending,
    revoked,
    load,
    start,
    revise,
    analyze,
    materialize,
    control,
    retry,
    newDraft,
  }
}
