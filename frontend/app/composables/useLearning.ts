import { api, ApiFailure } from '~/utils/api'
import type { LearningAsset, LearningMode, LearningView, SkillRevision } from '~/types/learning'

export function useLearning() {
  const shop = useShop()
  const data = ref<LearningView | null>(null),
    error = ref(''),
    busy = ref(false),
    unavailable = ref(false)
  type Submission = {
    path: string
    method: 'POST' | 'PATCH'
    body: Record<string, unknown>
    key: string
  }
  const pending = ref<Submission | null>(null)
  let epoch = 0
  const scope = computed(() =>
    [shop.s.storeId, shop.s.session?.principal_id, shop.s.session?.roles.join(',')].join(':'),
  )
  const root = () => `/api/v1/stores/${encodeURIComponent(shop.s.storeId)}/learning`
  async function load() {
    if (!shop.s.storeId) return
    const n = epoch
    try {
      const result = await api<LearningView>(root())
      if (n !== epoch) return
      data.value = result
      unavailable.value = false
      error.value = ''
    } catch (e) {
      if (n !== epoch) return
      data.value = null
      unavailable.value = e instanceof ApiFailure && e.code === 'LEARNING_DISABLED'
      error.value = unavailable.value ? '' : (e as Error).message
    }
  }
  async function submit(request: Submission) {
    if (
      busy.value ||
      !shop.hasRole('operator') ||
      (pending.value && pending.value.key !== request.key)
    )
      return
    const n = epoch
    busy.value = true
    pending.value = request
    error.value = ''
    try {
      await api(request.path, request.method, request.body, request.key)
      if (n !== epoch) return
      pending.value = null
      await load()
    } catch (e) {
      if (n !== epoch) return
      const message = (e as Error).message
      if (e instanceof ApiFailure && e.status >= 400 && e.status < 500) {
        pending.value = null
        await load()
      }
      error.value = message
    } finally {
      if (n === epoch) busy.value = false
    }
  }
  const send = (suffix: string, method: 'POST' | 'PATCH', body: Record<string, unknown>) =>
    submit({ path: root() + suffix, method, body, key: crypto.randomUUID() })
  const policy = (mode: LearningMode) =>
    data.value && send('/policy', 'PATCH', { mode, expected_version: data.value.policy.version })
  const evaluate = (asset: LearningAsset, rev: SkillRevision) =>
    send(`/assets/${asset.id}/evaluations`, 'POST', {
      expected_version: asset.version,
      revision: rev.revision,
    })
  const transition = (asset: LearningAsset, rev: SkillRevision, action: string) =>
    send(`/assets/${asset.id}/transitions`, 'POST', {
      expected_version: asset.version,
      revision: rev.revision,
      action,
      evaluation_id: rev.evaluation_id,
    })
  const forget = (asset: LearningAsset) =>
    data.value &&
    send('/forget', 'POST', { expected_version: data.value.policy.version, asset_id: asset.id })
  watch(
    scope,
    () => {
      epoch++
      data.value = null
      error.value = ''
      pending.value = null
      busy.value = false
      unavailable.value = false
      void load()
    },
    { immediate: true },
  )
  onUnmounted(() => {
    epoch++
  })
  return {
    data,
    error,
    busy,
    unavailable,
    pending,
    load,
    policy,
    evaluate,
    transition,
    forget,
    retry: () => pending.value && submit(pending.value),
  }
}
