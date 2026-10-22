<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { api, query, ApiFailure } from '~/utils/api'
import type { Schema } from '~/types/models'
import { sourceGroups, sourceIdentity, sourceLabel, type SourceGroup } from '~/utils/agent'
const props = defineProps<{ references: unknown[]; runId?: string }>()
const agent = useAgentConversation()
const demo = useDemoMode()
const dialog = ref<HTMLDialogElement | null>(null)
const excerpt = ref<Schema<'HistoricalEvidence'> | null>(null)
const loading = ref(false),
  error = ref('')
const downloading = ref(false),
  downloadStatus = ref('')
let downloadEpoch = 0
let downloadController: AbortController | null = null
function cancelDownload() {
  downloadEpoch++
  downloadController?.abort()
  downloadController = null
  downloading.value = false
  downloadStatus.value = ''
}
watch(
  () => !!excerpt.value,
  (available) => {
    if (!available) cancelDownload()
  },
)
async function downloadOriginal() {
  if (!excerpt.value || downloading.value || agent.s.accessRevoked) return
  const ref = excerpt.value.reference
  if (
    typeof ref.id !== 'string' ||
    typeof ref.version_id !== 'string' ||
    typeof ref.original_sha256 !== 'string'
  )
    return
  const captured = sourceIdentity(ref),
    epoch = ++downloadEpoch
  const path = `/api/v1/documents/${encodeURIComponent(ref.id)}/versions/${encodeURIComponent(ref.version_id)}`
  const controller = new AbortController()
  downloadController = controller
  const timeout = setTimeout(() => controller.abort(), 65000)
  const current = () =>
    epoch === downloadEpoch &&
    dialog.value?.open &&
    sourceIdentity(excerpt.value?.reference) === captured &&
    !agent.s.accessRevoked
  downloading.value = true
  downloadStatus.value = ''
  try {
    const version = await api<Schema<'Version'>>(path)
    if (!current()) return
    if (
      version.id !== ref.version_id ||
      version.document_id !== ref.id ||
      version.content_sha256 !== ref.original_sha256
    )
      throw Error('Version mismatch')
    const response = await fetch('/api/backend' + path + '/content', {
      signal: controller.signal,
      cache: 'no-store',
    })
    if (!response.ok) throw new ApiFailure('ORIGINAL_UNAVAILABLE', '', response.status)
    const blob = await response.blob()
    if (!current()) return
    const hash = Array.from(
      new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())),
    )
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('')
    if (blob.size !== version.size_bytes || hash !== ref.original_sha256)
      throw Error('Content mismatch')
    // Recheck authority after the transfer as well as before it.
    await api<Schema<'Version'>>(path)
    if (!current()) return
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = version.original_name
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    downloadStatus.value = '已交给浏览器保存此版本原件。'
  } catch (e) {
    if (current()) {
      downloadStatus.value =
        '无法下载此历史版本：访问权限、原件可用性或内容校验未通过，也可能是连接中断。请重试。'
      if (e instanceof ApiFailure && [401, 403, 404].includes(e.status)) {
        excerpt.value = null
        error.value = '此历史版本当前不可访问，已停止展示。未替换为最新版本。'
      }
    }
  } finally {
    clearTimeout(timeout)
    if (epoch === downloadEpoch) {
      downloading.value = false
      downloadController = null
    }
  }
}
let requestEpoch = 0
let selectedReference: Record<string, unknown> | null = null
let returnFocus: HTMLElement | null = null
function clear() {
  cancelDownload()
  requestEpoch++
  selectedReference = null
  excerpt.value = null
  error.value = ''
  loading.value = false
  dialog.value?.close()
}
watch(() => [props.runId, agent.s.epoch, agent.s.accessRevoked], clear)
onUnmounted(clear)
async function open(r: Record<string, unknown>, event: Event) {
  if (!props.runId || agent.s.accessRevoked) return
  selectedReference = r
  const epoch = ++requestEpoch
  returnFocus = event.currentTarget as HTMLElement
  excerpt.value = null
  error.value = ''
  loading.value = true
  dialog.value?.showModal()
  try {
    const params = Object.fromEntries(
      ['id', 'version_id', 'generation_id', 'chunk_id', 'metadata_revision', 'content_sha256'].map(
        (k) => [k, String(r[k] ?? '')],
      ),
    )
    const result = await api<Schema<'HistoricalEvidence'>>(
      `/api/v1/agent-runs/${encodeURIComponent(props.runId)}/evidence${query(params)}`,
    )
    if (epoch === requestEpoch) excerpt.value = result
  } catch {
    if (epoch === requestEpoch)
      error.value =
        '该历史片段暂不可用，可能已归档、删除、权限变化或记录校验未通过。未替换为最新版本。'
  } finally {
    if (epoch === requestEpoch) loading.value = false
  }
}
watch(
  () => agent.s.run,
  async () => {
    if (!dialog.value?.open || !selectedReference || !props.runId) return
    const epoch = ++requestEpoch
    const params = Object.fromEntries(
      ['id', 'version_id', 'generation_id', 'chunk_id', 'metadata_revision', 'content_sha256'].map(
        (k) => [k, String(selectedReference![k] ?? '')],
      ),
    )
    try {
      const result = await api<Schema<'HistoricalEvidence'>>(
        `/api/v1/agent-runs/${encodeURIComponent(props.runId)}/evidence${query(params)}`,
      )
      if (epoch === requestEpoch) {
        excerpt.value = result
        error.value = ''
      }
    } catch {
      if (epoch === requestEpoch) {
        excerpt.value = null
        error.value = '历史片段当前不可访问，或连接中断，已停止展示。请关闭后重新核对。'
      }
    } finally {
      if (epoch === requestEpoch) loading.value = false
    }
  },
)
function closed() {
  cancelDownload()
  requestEpoch++
  selectedReference = null
  excerpt.value = null
  returnFocus?.focus()
}
const items = computed(() => sourceGroups(props.references))
// A document reference carries no title; it is read once per document and shared by every
// answer. An empty title (still loading, or not readable) leaves the plain label; a read that
// failed for a passing reason is tried again with the next answer.
const titles = useState<Record<string, string>>('agent-document-titles', () => ({}))
watch(
  items,
  (groups) => {
    if (!import.meta.client) return
    for (const id of new Set(groups.map((g) => g.documentId))) {
      if (!id || id in titles.value) continue
      titles.value[id] = ''
      api<Schema<'Document'>>(`/api/v1/documents/${encodeURIComponent(id)}`)
        .then((d) => (titles.value[id] = d.title))
        .catch((e) => {
          if (!(e instanceof ApiFailure) || !e.status || e.status >= 500) delete titles.value[id]
        })
    }
  },
  { immediate: true },
)
const titleOf = (g: SourceGroup) => (g.documentId && titles.value[g.documentId]) || ''
const fields: Record<string, string> = {
  id: '来源编号',
  version_id: '文档版本',
  generation_id: '检索版本',
  chunk_id: '片段编号',
  metadata_revision: '资料信息版本',
  locator: '原文位置',
  plan_version: '方案版本',
  state_version: '状态版本',
  hash: '内容校验',
  content_hash: '内容校验',
  content_sha256: '片段校验',
  original_sha256: '原件校验',
}
const labels: Record<string, string> = {
  page: '页码',
  section: '章节',
  paragraph: '段落',
  line_start: '起始行',
  line_end: '结束行',
  sheet: '工作表',
  row: '行',
  paragraph_range: '段落范围',
  cell_range: '单元格',
  section_path: '章节',
  table: '表格',
}
const places = (v: object, keys?: readonly string[]) =>
  Object.entries(v)
    .filter(
      ([k, x]) =>
        labels[k] && (!keys || keys.includes(k)) && x != null && (!Array.isArray(x) || x.length),
    )
    .map(
      ([k, x]) =>
        `${tr(labels[k])} ${Array.isArray(x) ? x.join(k === 'section_path' ? ' / ' : '–') : String(x)}`,
    )
    .join(' · ')
const location = (v: unknown) => {
  if (typeof v === 'string') return v
  if (!v || typeof v !== 'object') return '未提供可读位置'
  return places(v) || '详见下方版本定位记录'
}
// Excerpts of one document are told apart by number only; section and sheet names, often in
// the document's own language, stay in the excerpt's full location.
const numbered = [
  'page',
  'paragraph',
  'paragraph_range',
  'line_start',
  'line_end',
  'row',
  'cell_range',
]
const spot = (v: unknown, i: number) =>
  (v && typeof v === 'object' && places(v, numbered)) || tr('片段 {0}', [i + 1])
const value = (v: unknown) => (typeof v === 'object' ? JSON.stringify(v) : String(v))
</script>
<template>
  <div v-if="items.length" class="agent-references" :aria-label="tr('本轮获取的来源')">
    <details v-for="g in items" :key="g.key" class="agent-source">
      <summary :title="titleOf(g) || undefined">
        <AppIcon name="file-text" />{{ tr(sourceLabel(g.parts[0]))
        }}<span v-if="titleOf(g)" class="agent-source-name">· {{ titleOf(g) }}</span
        ><span v-if="g.parts[0]!.version_id && !demo.enabled.value">{{ tr('· 有版本记录') }}</span
        ><AppIcon name="chevron-down" />
      </summary>
      <div class="agent-source-body">
        <p>{{ tr('本轮获取的来源，供核对使用。') }}</p>
        <template v-for="(r, i) in g.parts" :key="sourceIdentity(r)">
          <details v-if="!demo.enabled.value" class="tool-technical">
            <summary>
              {{
                g.parts.length > 1
                  ? joinText([tr('版本定位记录'), '·', spot(r.locator, i)])
                  : tr('版本定位记录')
              }}
            </summary>
            <dl>
              <template v-for="(label, field) in fields" :key="field"
                ><div v-if="r[field] != null">
                  <dt>{{ tr(label) }}</dt>
                  <dd>{{ value(r[field]) }}</dd>
                </div></template
              >
            </dl>
          </details>
          <button v-if="r.chunk_id && runId" class="text-link" @click="open(r, $event)">
            {{
              g.parts.length > 1
                ? joinText([tr('打开当时原文片段'), '·', spot(r.locator, i)])
                : tr('打开当时原文片段')
            }}
          </button>
          <p v-else-if="r.chunk_id">{{ tr('缺少运行关联，无法核对历史原文。') }}</p>
        </template>
      </div>
    </details>
    <dialog
      ref="dialog"
      class="evidence-dialog"
      :aria-label="tr('历史原文片段')"
      @close="closed"
      @click="$event.target === dialog && dialog?.close()"
    >
      <div class="evidence-dialog-content">
        <header>
          <h2>{{ tr('历史原文片段') }}</h2>
          <button class="text-link" autofocus @click="dialog?.close()">{{ tr('关闭原文') }}</button>
        </header>
        <p v-if="loading" role="status">{{ tr('正在核对历史版本与当前访问权限…') }}</p>
        <p v-if="error" role="alert">{{ tr(error) }}</p>
        <template v-if="excerpt">
          <h3>{{ excerpt.title }}</h3>
          <p>
            {{
              joinText([
                tr('原件 v{0}', [excerpt.version_no]),
                tr('· 本轮获取的来源，不代表逐句引用或当前有效条款。'),
              ])
            }}
          </p>
          <p>{{ joinText([tr('原文位置：'), tr(location(excerpt.reference.locator))]) }}</p>
          <pre class="evidence-text">{{ excerpt.text }}</pre>
          <button
            class="text-link evidence-download"
            :disabled="downloading"
            @click="downloadOriginal"
          >
            <AppIcon name="download" />{{
              tr(downloading ? '正在核对并下载…' : `下载原件 v${excerpt.version_no}`)
            }}
          </button>
          <p v-if="downloadStatus" role="status">{{ tr(downloadStatus) }}</p>
          <p v-if="excerpt.truncated">{{ tr('本片段已截断，并非完整原文。') }}</p>
          <details>
            <summary>{{ tr('核对版本与内容校验') }}</summary>
            <dl>
              <div v-for="(v, k) in excerpt.reference" :key="k">
                <dt>{{ tr(fields[k] || k) }}</dt>
                <dd>{{ value(v) }}</dd>
              </div>
            </dl>
          </details>
        </template>
      </div>
    </dialog>
  </div>
</template>
