import type { Schema, Session } from '~/types/models'
import { api, query, ApiFailure } from '~/utils/api'

type Document = Schema<'Document'>
type Version = Schema<'Version'>
type Pending = {
  key: string
  path: string
  method: 'POST' | 'PATCH'
  body: Record<string, unknown>
  title: string
  file?: { name: string; size: number; hash: string }
}
const maxFileBytes = 20 * 1024 * 1024
export const documentCategories: Record<string, string> = {
  general: '其他资料',
  supplier_terms: '供应商条款',
  product: '商品说明',
  sop: '操作手册',
  campaign: '活动资料',
  review: '经营复盘',
}
export const documentCategory = (value: string) => documentCategories[value] || value
export function fileSize(bytes: number) {
  return bytes < 1024
    ? `${bytes} B`
    : bytes < 1024 * 1024
      ? `${(bytes / 1024).toFixed(1)} KB`
      : `${(bytes / 1024 / 1024).toFixed(1)} MiB`
}
export function documentError(error: unknown) {
  const e = error as {
    code?: string
    status?: number
    statusCode?: number
    message?: string
    data?: { error?: { code?: string; message?: string }; statusMessage?: string }
  }
  const code = e.code || e.data?.error?.code
  const messages: Record<string, string> = {
    METADATA_VERSION_CONFLICT: '资料已被其他操作更新。请载入最新资料后重新核对。',
    DOCUMENT_ARCHIVED: '资料已归档，请刷新列表；恢复后才能上传新版本。',
    INVALID_DOCUMENT_STATE: '资料状态已变化，请刷新后重新核对。',
    RESOURCE_NOT_FOUND: '资料不存在或已无权访问，请刷新列表。',
    FORBIDDEN: '当前身份无权执行此操作。',
    UNAUTHENTICATED: '身份已失效，请重新连接后端。',
    ORIGINAL_UNAVAILABLE: '原件暂时不可用，请稍后重试或联系资料维护者。',
    IDEMPOTENCY_KEY_REUSED: '原提交与本次内容不一致，请先核实原提交。',
    VALIDATION_ERROR: '资料格式或填写内容不符合要求，请检查文件、必填项和有效期。',
    INVALID_UPLOAD: '原件格式无效、已加密或文件损坏，请检查后重新选择。文本资料需要UTF-8编码。',
    UPLOAD_TOO_LARGE: '文件不能超过20 MiB。',
    BACKEND_UNAVAILABLE: '暂未取得结果，请核实原提交或稍后重试。',
  }
  return (
    messages[code || ''] ||
    (e.statusCode === 413 ? '文件不能超过20 MiB。' : '') ||
    e.data?.error?.message ||
    e.data?.statusMessage ||
    e.message ||
    '暂时未取得结果，请重试。'
  )
}

export function useDocuments(storeId: string, session: Session) {
  const documents = ref<Document[]>([]),
    selected = ref<Document | null>(null)
  const versions = ref<Version[]>([]),
    cursor = ref<string | null>(null),
    versionCursor = ref<string | null>(null)
  const loading = ref(false),
    detailLoading = ref(false),
    busy = ref(false),
    downloading = ref('')
  const error = ref(''),
    detailError = ref(''),
    notice = ref(''),
    pendingError = ref('')
  const pending = ref<Pending | null>(null)
  const filters = reactive({ q: '', category: '', status: 'active', sku_id: '', supplier_id: '' })
  let applied = { ...filters },
    listSeq = 0,
    detailSeq = 0,
    alive = true
  let original: File | undefined
  const storageKey = `ss.documents.${encodeURIComponent(session.principal_id)}.${encodeURIComponent(storeId)}`
  const canWrite = computed(() => session.roles.some((r) => ['operator', 'admin'].includes(r)))
  const ownsAccess = (doc: Document) =>
    doc.visibility === 'store' || doc.owner_principal_id === session.principal_id
  const canRead = (doc: Document) => doc.status === 'active' && ownsAccess(doc)
  const canManage = (doc: Document) => canWrite.value && ownsAccess(doc)
  function clearSelection() {
    detailSeq++
    selected.value = null
    versions.value = []
    versionCursor.value = null
    detailError.value = ''
    detailLoading.value = false
  }
  async function loadList(more = false) {
    if (!storeId || (more && (!cursor.value || loading.value))) return
    const seq = ++listSeq
    if (!more) applied = { ...filters }
    loading.value = true
    error.value = ''
    try {
      const result = await api<Schema<'DocumentList'>>(
        `/api/v1/stores/${storeId}/documents` +
          query({
            ...Object.fromEntries(Object.entries(applied).filter(([, v]) => v)),
            cursor: more ? cursor.value : undefined,
            limit: 20,
          }),
      )
      if (!alive || seq !== listSeq) return
      documents.value = more
        ? [
            ...documents.value,
            ...result.items.filter((d) => !documents.value.some((old) => old.id === d.id)),
          ]
        : result.items
      cursor.value = result.next_cursor
    } catch (e) {
      if (!alive || seq !== listSeq) return
      error.value = documentError(e)
      if (e instanceof ApiFailure && [401, 403, 404].includes(e.status)) {
        documents.value = []
        cursor.value = null
        clearSelection()
      }
    } finally {
      if (alive && seq === listSeq) loading.value = false
    }
  }
  async function select(id: string) {
    clearSelection()
    const seq = ++detailSeq
    detailLoading.value = true
    try {
      const doc = await api<Document>(`/api/v1/documents/${id}`)
      if (!alive || seq !== detailSeq) return
      selected.value = doc
      if (canRead(doc)) {
        const result = await api<Schema<'VersionList'>>(`/api/v1/documents/${id}/versions?limit=20`)
        if (!alive || seq !== detailSeq) return
        versions.value = result.items
        versionCursor.value = result.next_cursor
      }
    } catch (e) {
      if (!alive || seq !== detailSeq) return
      versions.value = []
      versionCursor.value = null
      detailError.value = documentError(e)
      if (e instanceof ApiFailure && [401, 403, 404].includes(e.status)) selected.value = null
    } finally {
      if (alive && seq === detailSeq) detailLoading.value = false
    }
  }
  async function moreVersions() {
    const doc = selected.value,
      seq = detailSeq
    if (!doc || !versionCursor.value || detailLoading.value) return
    detailLoading.value = true
    detailError.value = ''
    try {
      const result = await api<Schema<'VersionList'>>(
        `/api/v1/documents/${doc.id}/versions` + query({ cursor: versionCursor.value, limit: 20 }),
      )
      if (!alive || seq !== detailSeq) return
      versions.value.push(
        ...result.items.filter((v) => !versions.value.some((old) => old.id === v.id)),
      )
      versionCursor.value = result.next_cursor
    } catch (e) {
      if (alive && seq === detailSeq) detailError.value = documentError(e)
    } finally {
      if (alive && seq === detailSeq) detailLoading.value = false
    }
  }
  async function fingerprint(file: File) {
    if (!file.size || file.size > maxFileBytes) throw Error('请选择非空且不超过20 MiB的文件。')
    if (!/\.(pdf|docx|xlsx|csv|md|txt)$/i.test(file.name))
      throw Error('支持PDF、Word、Excel、CSV、Markdown和TXT。')
    const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
    return {
      name: file.name,
      size: file.size,
      hash: Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join(''),
    }
  }
  function forget() {
    try {
      sessionStorage.removeItem(storageKey)
    } catch {
      /* A stale receipt can safely replay. */
    }
    pending.value = null
    original = undefined
  }
  async function sendPending(file?: File) {
    const command = pending.value
    if (!alive || !command || busy.value) return null
    busy.value = true
    pendingError.value = ''
    try {
      let body: FormData | Record<string, unknown> = command.body
      if (command.file) {
        const source = file || original
        if (!source) throw Error('请重新选择原文件以核实提交；内容和文件名必须与上次一致。')
        const check = await fingerprint(source)
        if (
          check.name !== command.file.name ||
          check.hash !== command.file.hash ||
          check.size !== command.file.size
        )
          throw Error('文件与原提交不一致。请选择原文件，不能用新文件重试旧提交。')
        original = source
        body = new FormData()
        body.append('file', source)
        body.append('metadata', JSON.stringify(command.body))
      }
      if (!alive) return null
      const doc = await $fetch<Document>('/api/backend' + command.path, {
        method: command.method,
        body,
        headers: { 'Idempotency-Key': command.key },
        retry: 0,
        timeout: 65000,
      })
      forget()
      if (alive) {
        notice.value = '提交已确认，资料已保存。'
        await loadList()
        await select(doc.id) // A replay may contain historical metadata; always re-read.
      }
      return doc
    } catch (e) {
      const status = (e as { statusCode?: number }).statusCode || 0
      if (status >= 400 && status < 500 && ![401, 403, 404, 408, 429].includes(status)) forget()
      if (alive) pendingError.value = documentError(e)
      return null
    } finally {
      if (alive) busy.value = false
    }
  }
  async function save(
    path: string,
    method: 'POST' | 'PATCH',
    body: Record<string, unknown>,
    title: string,
    file?: File,
  ) {
    if (!alive || pending.value || busy.value) return null
    const descriptor = file ? await fingerprint(file) : undefined
    if (!alive) return null
    const command: Pending = {
      key: crypto.randomUUID(),
      path,
      method,
      body: structuredClone(body),
      title,
      file: descriptor,
    }
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(command))
    } catch {
      throw Error('浏览器无法保存本次提交的恢复记录。请允许会话存储后再提交。')
    }
    pending.value = command
    original = file
    return sendPending()
  }
  async function download(version: Version) {
    if (downloading.value) return
    const seq = detailSeq
    downloading.value = version.id
    detailError.value = ''
    try {
      const response = await fetch(
        `/api/backend/api/v1/documents/${version.document_id}/versions/${version.id}/content`,
        { signal: AbortSignal.timeout(65000), cache: 'no-store' },
      )
      if (!response.ok) throw { statusCode: response.status, data: await response.json() }
      const blob = await response.blob()
      if (!alive || seq !== detailSeq) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = version.original_name
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      if (alive && seq === detailSeq) detailError.value = documentError(e)
    } finally {
      if (alive) downloading.value = ''
    }
  }
  function warnLeaving(event: BeforeUnloadEvent) {
    if (pending.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null') as Pending | null
      if (
        saved?.key &&
        saved.body &&
        ['POST', 'PATCH'].includes(saved.method) &&
        (saved.path === `/api/v1/stores/${storeId}/documents` ||
          /^\/api\/v1\/documents\/[A-Za-z0-9_-]+(\/versions|\/control)?$/.test(saved.path))
      )
        pending.value = saved
    } catch {
      /* Browsing stays available without session storage. */
    }
    window.addEventListener('beforeunload', warnLeaving)
    void loadList()
  })
  onUnmounted(() => {
    alive = false
    listSeq++
    detailSeq++
    window.removeEventListener('beforeunload', warnLeaving)
  })
  return {
    documents,
    selected,
    versions,
    cursor,
    versionCursor,
    loading,
    detailLoading,
    busy,
    downloading,
    error,
    detailError,
    notice,
    pendingError,
    pending,
    filters,
    canWrite,
    canRead,
    canManage,
    loadList,
    clearSelection,
    select,
    moreVersions,
    save,
    sendPending,
    download,
  }
}
