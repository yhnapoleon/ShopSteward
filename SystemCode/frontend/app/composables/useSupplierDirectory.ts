import type { Ref } from 'vue'
import { api } from '~/utils/api'
import { rememberSupplierNames } from '~/utils/glossary'
import type { Schema } from '~/types/models'

// The suppliers the current store has documents for (sourcing reads them). Read once per store,
// together with the store's own data (useShop.refresh), so every card says "Baichuan Wholesale"
// instead of the supplier id from its first paint.

/** The district the sample documents are written for; a place name, so it is not translated. */
export const SAMPLE_DISTRICT = '滨江区'

export type DirectoryState = {
  storeId: string
  suppliers: Schema<'SupplierDocuments'>[]
  loaded: boolean
  loading: boolean
  error: string
  /** Failed reads in a row, and when the next one may go out (doubling, at most 5 minutes). */
  failures?: number
  retryAt?: number
}
/** The shared state's key: useShop and the restock flow read the same directory. */
export const DIRECTORY_STATE = 'supplier-directory'
export const emptyDirectory = (): DirectoryState => ({
  storeId: '',
  suppliers: [],
  loaded: false,
  loading: false,
  error: '',
})
const path = (store: string) => `/api/v1/stores/${encodeURIComponent(store)}/supplier-documents`
function apply(state: Ref<DirectoryState>, set: Schema<'SupplierDocumentSet'>) {
  state.value.suppliers = set.suppliers
  state.value.loaded = true
  rememberSupplierNames(set.suppliers)
}
// One read per store at a time: a second caller waits for the read already under way.
let reading: { store: string; promise: Promise<void> } | null = null
/**
 * Read the store's supplier documents into the shared state, once per store (or again when
 * forced). `current` is the store selected now: an answer for another store is dropped.
 */
export function fetchDirectory(
  state: Ref<DirectoryState>,
  store: string,
  current: () => string,
  force = false,
): Promise<void> {
  if (state.value.storeId !== store) {
    state.value = { ...emptyDirectory(), storeId: store }
    rememberSupplierNames([], true)
  }
  if (reading?.store === store) return reading.promise
  if (state.value.loaded && !force) return Promise.resolve()
  if (!force && (state.value.retryAt ?? 0) > Date.now()) return Promise.resolve()
  state.value.loading = true
  state.value.error = ''
  const entry = { store, promise: Promise.resolve() }
  entry.promise = (async () => {
    try {
      const set = await api<Schema<'SupplierDocumentSet'>>(path(store))
      if (store === current() && state.value.storeId === store) {
        apply(state, set)
        state.value.failures = 0
        state.value.retryAt = 0
      }
    } catch (e) {
      if (state.value.storeId === store) {
        const failures = (state.value.failures ?? 0) + 1
        state.value.error = (e as Error).message
        state.value.failures = failures
        state.value.retryAt = Date.now() + Math.min(300_000, 5000 * 2 ** (failures - 1))
      }
    } finally {
      if (state.value.storeId === store) state.value.loading = false
      if (reading === entry) reading = null
    }
  })()
  reading = entry
  return entry.promise
}

export function useSupplierDirectory() {
  const shop = useShop()
  const state = useState<DirectoryState>(DIRECTORY_STATE, emptyDirectory)
  async function load(force = false) {
    const store = shop.s.storeId
    if (!store || !shop.s.session?.sourcing) return
    await fetchDirectory(state, store, () => shop.s.storeId, force)
  }
  /** Three invented suppliers' documents about this item, for trying the flow. */
  async function loadSample(skuId: string) {
    const store = shop.s.storeId
    if (!store || !skuId) return
    state.value.loading = true
    state.value.error = ''
    try {
      const set = await api<Schema<'SupplierDocumentSet'>>(path(store) + '/sample', 'POST', {
        sku_id: skuId,
        district: SAMPLE_DISTRICT,
      })
      if (store === shop.s.storeId) apply(state, set)
    } catch (e) {
      state.value.error = (e as Error).message
      throw e
    } finally {
      state.value.loading = false
    }
  }
  /** Suppliers whose documents a reviewer can read; a connected supplier keeps its own offer. */
  const readable = computed(() => state.value.suppliers.filter((s) => !s.connected))
  /** Learn names that arrive with a sourcing run (the reviewers' cards carry them). */
  const learn = (entries: { supplier_id: string; name?: string | null }[]) =>
    rememberSupplierNames(entries)
  return { state, load, loadSample, readable, learn }
}
