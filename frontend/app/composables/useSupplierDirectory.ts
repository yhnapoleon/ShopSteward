import { api } from '~/utils/api'
import { rememberSupplierNames } from '~/utils/glossary'
import type { Schema } from '~/types/models'

// The suppliers the current store has documents for (sourcing reads them). Read once per store;
// their names are registered so every card says "百川批发" instead of the supplier id.

/** The district the sample documents are written for; a place name, so it is not translated. */
export const SAMPLE_DISTRICT = '滨江区'

export function useSupplierDirectory() {
  const shop = useShop()
  const state = useState('supplier-directory', () => ({
    storeId: '',
    suppliers: [] as Schema<'SupplierDocuments'>[],
    loaded: false,
    loading: false,
    error: '',
  }))
  const path = (store: string) => `/api/v1/stores/${encodeURIComponent(store)}/supplier-documents`
  function apply(store: string, set: Schema<'SupplierDocumentSet'>) {
    if (store !== shop.s.storeId) return
    state.value.suppliers = set.suppliers
    state.value.loaded = true
    rememberSupplierNames(set.suppliers)
  }
  async function load(force = false) {
    const store = shop.s.storeId
    if (!store || !shop.s.session?.sourcing) return
    if (state.value.storeId !== store) {
      state.value.storeId = store
      state.value.suppliers = []
      state.value.loaded = false
      rememberSupplierNames([], true)
    }
    if ((state.value.loaded && !force) || state.value.loading) return
    state.value.loading = true
    state.value.error = ''
    try {
      apply(store, await api<Schema<'SupplierDocumentSet'>>(path(store)))
    } catch (e) {
      state.value.error = (e as Error).message
    } finally {
      state.value.loading = false
    }
  }
  /** Three invented suppliers' documents about this item, for trying the flow. */
  async function loadSample(skuId: string) {
    const store = shop.s.storeId
    if (!store || !skuId) return
    state.value.loading = true
    state.value.error = ''
    try {
      apply(
        store,
        await api<Schema<'SupplierDocumentSet'>>(path(store) + '/sample', 'POST', {
          sku_id: skuId,
          district: SAMPLE_DISTRICT,
        }),
      )
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
