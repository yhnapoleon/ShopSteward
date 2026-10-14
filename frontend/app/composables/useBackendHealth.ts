type Reachability = 'unknown' | 'ok' | 'unreachable'

/**
 * Backend reachability, kept apart from identity: an outage must never read as
 * "connect your identity". Only the owner (the page) probes; other callers read the state.
 *
 * Probes every 5 s, and only while the session is unauthenticated for an unknown/unreachable
 * reason, or while business reads are failing. On recovery an open store only needs a forced
 * refresh, which keeps the selected store and mission; otherwise the caller's `resume` runs
 * (default `shop.init()`).
 */
export function useBackendHealth(owner = false, resume?: () => Promise<unknown>) {
  const shop = useShop()
  const h = useState('backend-health', () => ({
    backend: 'unknown' as Reachability,
    checkedAt: '',
    probing: false,
    resuming: false,
  })).value
  const unreachable = computed(() => h.backend === 'unreachable')
  const needed = computed(
    () =>
      !shop.s.loading &&
      ((shop.s.session?.authenticated === false && h.backend !== 'ok') ||
        (!shop.s.connected && Boolean(shop.s.error))),
  )
  async function probe() {
    if (h.probing || h.resuming) return
    h.probing = true
    const before = h.backend
    try {
      const r = await $fetch<{ backend?: string }>('/api/health', { retry: 0, timeout: 8000 })
      if (r?.backend === 'ok' || r?.backend === 'unreachable') h.backend = r.backend
    } catch (e) {
      // No HTTP response at all: the page's own server cannot be reached either.
      if (!(e as { response?: unknown }).response) h.backend = 'unreachable'
    } finally {
      h.checkedAt = new Date().toISOString()
      h.probing = false
    }
    if (before === 'unreachable' && h.backend === 'ok') await recover()
  }
  async function recover() {
    h.resuming = true
    try {
      // A store that was already open only needs fresh reads; otherwise redo the first load.
      if (shop.s.session?.authenticated && shop.s.storeId) await shop.refresh(true)
      else await (resume ? resume() : shop.init())
    } finally {
      h.resuming = false
    }
  }
  if (owner) {
    let timer: ReturnType<typeof setInterval> | undefined
    // The session read already knows whether nothing answered; use it before the first probe.
    watch(
      () => shop.s.session,
      (session) => {
        const hint = (session as { backend?: Reachability } | null)?.backend
        if (session?.authenticated) h.backend = 'ok'
        else if (hint === 'ok' || hint === 'unreachable') h.backend = hint
      },
    )
    // A successful business read proves the backend answered, even if polling got there first.
    watch(
      () => shop.s.connected,
      (connected) => {
        if (connected) h.backend = 'ok'
      },
    )
    watch(needed, (value) => {
      if (value) void probe()
    })
    onMounted(() => {
      timer = setInterval(() => {
        if (needed.value) void probe()
      }, 5000)
    })
    onUnmounted(() => clearInterval(timer))
  }
  return { s: h, unreachable, probe }
}
