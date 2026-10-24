import type { Schema } from '~/types/models'
import { api, query } from '~/utils/api'

type Entry = Schema<'TimelineEntry'>
const wanted = 10,
  pageSize = 30,
  maxPages = 10

/**
 * "My decisions" for the current mission. Owner actions are sparse in a timeline full of
 * background checks, so pages are read until enough of them are found, there are no more
 * pages, or one round has read ten pages. Newer decisions from the shared timeline poll are
 * merged in, so the list stays current without re-reading history.
 */
export function useDecisionRecords(active: () => boolean) {
  const shop = useShop()
  const state = reactive({
    entries: [] as Entry[],
    cursor: null as string | null,
    scope: '',
    loading: false,
    loaded: false,
    error: '',
  })
  let epoch = 0
  const scope = () => (shop.s.missionId ? shop.s.storeVersion + ':' + shop.s.missionId : '')
  const items = computed(() => {
    const seen = new Set<string>()
    const fresh = state.scope === scope() ? state.entries : []
    return [...shop.s.timeline.filter((e) => e.mission_id === shop.s.missionId), ...fresh]
      .filter((e) => e.actor_type === 'USER' && !seen.has(e.id) && Boolean(seen.add(e.id)))
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  })
  async function load(more = false) {
    const key = scope(),
      missionId = shop.s.missionId
    if (!key) return
    if (more && (state.scope !== key || state.loading || !state.cursor)) return
    if (!more) {
      epoch++
      Object.assign(state, { entries: [], cursor: null, scope: key, loaded: false })
    }
    const run = epoch
    let cursor = more ? state.cursor : null,
      found = 0,
      pages = 0
    state.loading = true
    state.error = ''
    try {
      do {
        const page = await api<Schema<'TimelineEntryList'>>(
          `/api/v1/missions/${encodeURIComponent(missionId)}/timeline` +
            query({ cursor, limit: pageSize }),
        )
        if (run !== epoch || key !== scope()) return
        const decisions = page.items.filter((e) => e.actor_type === 'USER')
        state.entries.push(...decisions)
        found += decisions.length
        cursor = page.next_cursor
        state.cursor = cursor
        pages++
      } while (cursor && found < wanted && pages < maxPages)
      state.loaded = true
    } catch (e) {
      if (run === epoch) state.error = (e as Error).message
    } finally {
      if (run === epoch) state.loading = false
    }
  }
  watch(
    () => [active(), scope()] as const,
    ([on, key]) => {
      if (on && key && (state.scope !== key || (!state.loaded && !state.loading && !state.error)))
        void load()
    },
    { immediate: true },
  )
  return { state, items, load, more: () => load(true) }
}
