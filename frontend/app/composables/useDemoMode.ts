import { storeDisplayName } from '~/utils/glossary'

// Demo mode (workspace redesign §10): for an audience the page shows a presenter bar, plain store
// names and a "demo" badge instead of debugging labels. It changes no business rule, clock or
// data. Chosen in settings or with `?demo=1` (remembered in this browser; `?demo=0` turns it off).

const MODE_KEY = 'ss.demo.v1'
// Creation times of sample stores seen in demo mode, so the store list can name them.
const CREATED_KEY = 'ss.store-created.v1'
type StoreLike = { store_id: string; simulation_time?: string | null }

export function useDemoMode() {
  const state = useState('demo-mode', () => ({
    enabled: false,
    ready: false,
    saveFailed: false,
    created: {} as Record<string, string>,
  }))
  const route = useRoute()
  const { s } = useShop()
  function persist(on: boolean) {
    try {
      if (on) localStorage.setItem(MODE_KEY, '1')
      else localStorage.removeItem(MODE_KEY)
      state.value.saveFailed = false
    } catch {
      state.value.saveFailed = true
    }
  }
  if (import.meta.client && !state.value.ready) {
    state.value.ready = true
    let on = false
    try {
      on = localStorage.getItem(MODE_KEY) === '1'
      const created = JSON.parse(localStorage.getItem(CREATED_KEY) || '{}')
      if (created && typeof created === 'object' && !Array.isArray(created))
        state.value.created = created
    } catch {}
    const flag = route.query.demo
    if (flag === '1' || flag === '0') {
      on = flag === '1'
      persist(on)
    }
    state.value.enabled = on
    // Another tab of the same browser switched it.
    window.addEventListener('storage', (event) => {
      if (event.key === MODE_KEY) state.value.enabled = event.newValue === '1'
    })
  }
  const enabled = computed(() => state.value.enabled)
  const saveFailed = computed(() => state.value.saveFailed)
  function set(on: boolean) {
    state.value.enabled = on
    persist(on)
  }
  function toggle() {
    set(!state.value.enabled)
  }
  /** The selected store's opening ledger entry carries the moment the sample store was created. */
  function opening() {
    const entry = s.ledger.find((e) => e.effect_type === 'INIT')
    return entry?.simulation_time || entry?.occurred_at || ''
  }
  /** Keep the selected store's creation time for naming it in the store list later. */
  function remember() {
    const at = opening()
    if (!s.storeId || !at || state.value.created[s.storeId] === at) return
    const next = { ...state.value.created, [s.storeId]: at }
    const keys = Object.keys(next)
    if (keys.length > 100) delete next[keys[0]!]
    state.value.created = next
    try {
      localStorage.setItem(CREATED_KEY, JSON.stringify(next))
    } catch {}
  }
  /** "示例店铺 · 10/14 15:26" by creation time; without one known, by the store's business time. */
  function storeLabel(store: StoreLike) {
    const created =
      (store.store_id === s.storeId && opening()) || state.value.created[store.store_id]
    return storeDisplayName(
      { store_id: store.store_id, simulation_time: store.simulation_time, created_at: created },
      true,
    )
  }
  return { enabled, saveFailed, set, toggle, remember, storeLabel }
}
