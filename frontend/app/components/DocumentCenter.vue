<script setup lang="ts">
import type { Schema, Session } from '~/types/models'
import {
  documentCategories,
  documentCategory,
  documentError,
  fileSize,
} from '~/composables/useDocuments'
import { when } from '~/utils/presentation'

const props = defineProps<{
  storeId: string
  session: Session
  catalog: Schema<'Catalog'> | null
}>()
const emit = defineEmits<{ navigate: [view: string] }>()
const library = useDocuments(props.storeId, props.session)
const {
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
} = library
const mode = ref<'' | 'create' | 'append' | 'edit' | 'archive' | 'restore'>('')
const formError = ref(''),
  preparing = ref(false),
  upload = ref<File>(),
  recoveryFile = ref<File>()
const detailPane = ref<HTMLElement>()
const form = reactive({
  title: '',
  category: 'general',
  visibility: 'store' as 'store' | 'private',
  sku_ids: [] as string[],
  supplier_ids: [] as string[],
  valid_from: '',
  valid_until: '',
})
let editId = '',
  editVersion = 0
const dialogTitle = computed(
  () =>
    ({
      create: '上传资料',
      append: '上传新版本',
      edit: '编辑资料信息',
      archive: '归档这份资料？',
      restore: '恢复这份资料？',
      '': '店铺资料',
    })[mode.value],
)
const fileMode = computed(() => mode.value === 'create' || mode.value === 'append')
const metaMode = computed(() => mode.value === 'create' || mode.value === 'edit')
const locked = computed(() => busy.value || preparing.value)
const catalog = computed(() => (props.catalog?.store_id === props.storeId ? props.catalog : null))
const suppliers = computed(() => [
  ...new Set(catalog.value?.offers.map((o) => o.supplier_id) || []),
])
const products = computed(() => catalog.value?.products || [])
const categoryOptions = computed(() => [
  ...new Set([
    ...Object.keys(documentCategories),
    ...documents.value.map((d) => d.category),
    ...(selected.value ? [selected.value.category] : []),
  ]),
])
function open(next: typeof mode.value) {
  if (pending.value || locked.value) return
  mode.value = next
  formError.value = pendingError.value = ''
  upload.value = undefined
  const d = next === 'create' ? null : selected.value
  editId = d?.id || ''
  editVersion = d?.metadata_version || 0
  Object.assign(form, {
    title: d?.title || '',
    category: d?.category || 'general',
    visibility: d?.visibility || 'store',
    sku_ids: [...(d?.sku_ids || [])],
    supplier_ids: [...(d?.supplier_ids || [])],
    valid_from: '',
    valid_until: '',
  })
}
function picked(event: Event, recovery = false) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (recovery) recoveryFile.value = file
  else {
    upload.value = file
    if (file && mode.value === 'create' && !form.title)
      form.title = file.name.replace(/\.[^.]+$/, '').slice(0, 300)
  }
}
async function choose(id: string) {
  await library.select(id)
  if (selected.value && window.matchMedia('(max-width: 960px)').matches) {
    await nextTick()
    detailPane.value?.scrollIntoView({ behavior: 'instant', block: 'start' })
    detailPane.value?.focus({ preventScroll: true })
  }
}
function search() {
  library.clearSelection()
  void library.loadList()
}
async function reloadForm() {
  const currentMode = mode.value
  await library.select(editId)
  if (selected.value) open(currentMode)
  else mode.value = ''
}
async function submit() {
  if (locked.value) return
  formError.value = ''
  if (pending.value) {
    if (await library.sendPending(upload.value)) mode.value = ''
    return
  }
  preparing.value = true
  try {
    const metadata = {
      title: form.title.trim(),
      category: form.category.trim(),
      visibility: form.visibility,
      sku_ids: [...form.sku_ids],
      supplier_ids: [...form.supplier_ids],
    }
    const validity = {
      valid_from: form.valid_from ? new Date(form.valid_from).toISOString() : null,
      valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null,
    }
    if (validity.valid_from && validity.valid_until && validity.valid_until <= validity.valid_from)
      throw Error('失效时间必须晚于生效时间。')
    if (fileMode.value && !upload.value) throw Error('请先选择原件。')
    let path = `/api/v1/documents/${editId}`,
      body: Record<string, unknown>
    if (mode.value === 'create') {
      path = `/api/v1/stores/${props.storeId}/documents`
      body = { ...metadata, ...validity }
    } else if (mode.value === 'append') {
      path += '/versions'
      body = { expected_metadata_version: editVersion, ...validity }
    } else if (mode.value === 'edit') body = { ...metadata, expected_metadata_version: editVersion }
    else {
      path += '/control'
      body = { operation: mode.value, expected_metadata_version: editVersion }
    }
    const result = await library.save(
      path,
      mode.value === 'edit' ? 'PATCH' : 'POST',
      body,
      form.title || selected.value?.title || '资料',
      fileMode.value ? upload.value : undefined,
    )
    if (result) mode.value = ''
  } catch (e) {
    formError.value = documentError(e)
  } finally {
    preparing.value = false
  }
}
</script>

<template>
  <section class="document-center" aria-label="文档中心">
    <button class="text-link dc-back" :disabled="locked" @click="emit('navigate', 'today')">
      <AppIcon name="chevron-right" />返回今日
    </button>
    <header class="dc-header">
      <div>
        <div class="eyebrow">我的经营空间 · 资料</div>
        <h1>把依据，留在手边。</h1>
        <p>供货条款、商品说明与活动资料，在这里保存、整理和查阅。</p>
      </div>
      <button
        v-if="canWrite && storeId"
        class="primary"
        :disabled="locked || !!pending"
        @click="open('create')"
      >
        <AppIcon name="plus" />上传资料
      </button>
    </header>
    <div class="dc-scope">
      <AppIcon name="file-check-2" /><span
        >原件与版本可管理、下载。智能检索与 Agent 引用尚未接入。</span
      >
    </div>
    <div v-if="notice" class="dc-notice" role="status">
      <AppIcon name="check" /><span>{{ notice }}</span
      ><button class="icon-btn" aria-label="关闭资料提示" @click="notice = ''">
        <AppIcon name="x" />
      </button>
    </div>
    <section v-if="pending" class="dc-recovery notice amber" aria-label="待核实的资料提交">
      <h3>{{ busy ? '正在提交资料…' : '还有一笔资料提交待核实' }}</h3>
      <p>
        {{ pending.title }}<span v-if="pending.file"> · {{ pending.file.name }}</span>
      </p>
      <p>先核实原提交，再开始新的操作。重试会沿用同一提交标识。</p>
      <template v-if="!busy">
        <label v-if="pending.file" class="dc-field"
          >重新选择原文件（刷新页面后需要）
          <input
            type="file"
            accept=".pdf,.docx,.xlsx,.csv,.md,.txt"
            @change="picked($event, true)"
          />
        </label>
        <button class="secondary" @click="library.sendPending(recoveryFile)">核实原提交</button>
      </template>
      <p v-if="pendingError" role="alert">{{ pendingError }}</p>
    </section>
    <p v-if="pendingError && !pending && !mode" class="notice amber" role="alert">
      {{ pendingError }}
    </p>
    <div v-if="!storeId" class="dc-empty glass">
      <AppIcon name="file-text" />
      <h2>先选择经营环境</h2>
      <p>资料会保存在所选店铺中。</p>
    </div>
    <template v-else>
      <form class="dc-filters" aria-label="筛选资料" @submit.prevent="search">
        <label class="dc-search"
          ><span class="dc-label">搜索标题</span>
          <div>
            <AppIcon name="search" /><input
              v-model="filters.q"
              type="search"
              maxlength="300"
              placeholder="查找一份资料…"
            /></div
        ></label>
        <label
          ><span class="dc-label">分类</span
          ><select v-model="filters.category" @change="search">
            <option value="">全部分类</option>
            <option v-for="c in categoryOptions" :key="c" :value="c">
              {{ documentCategory(c) }}
            </option>
          </select></label
        >
        <label
          ><span class="dc-label">状态</span
          ><select v-model="filters.status" @change="search">
            <option value="active">使用中</option>
            <option value="archived">已归档</option>
          </select></label
        >
        <button type="submit" class="secondary" :disabled="loading">查找</button>
        <details class="dc-extra-filters">
          <summary>关联筛选</summary>
          <div class="dc-filter-entities">
            <label
              >商品<select v-model="filters.sku_id" @change="search">
                <option value="">全部商品</option>
                <option v-for="p in products" :key="p.sku_id" :value="p.sku_id">
                  {{ p.name }}
                </option>
              </select></label
            >
            <label
              >供应商<select v-model="filters.supplier_id" @change="search">
                <option value="">全部供应商</option>
                <option v-for="id in suppliers" :key="id" :value="id">{{ id }}</option>
              </select></label
            >
          </div>
        </details>
      </form>
      <div class="dc-workspace">
        <section class="dc-library glass" aria-label="资料列表" :aria-busy="loading">
          <header class="dc-section-head">
            <h2>{{ filters.status === 'archived' ? '归档资料' : '店铺资料' }}</h2>
            <span>{{ documents.length }} 份已载入</span
            ><button
              class="icon-btn"
              aria-label="刷新资料列表"
              :disabled="loading"
              @click="library.loadList()"
            >
              <AppIcon name="refresh-cw" />
            </button>
          </header>
          <div v-if="error" class="notice amber" role="alert">
            <p>{{ error }}</p>
            <button class="text-link" @click="library.loadList()">重新读取</button>
          </div>
          <div v-if="loading && !documents.length" class="dc-empty" role="status">
            <p>正在读取资料…</p>
          </div>
          <div v-else-if="!documents.length && !error" class="dc-empty">
            <AppIcon name="file-text" />
            <h3>
              {{
                filters.q || filters.category || filters.sku_id || filters.supplier_id
                  ? '没有找到匹配资料'
                  : filters.status === 'archived'
                    ? '还没有归档资料'
                    : '从第一份资料开始'
              }}
            </h3>
            <p>
              {{
                filters.status === 'archived'
                  ? '归档资料保留记录，恢复后可继续查阅原件。'
                  : '支持 PDF、Word、Excel、CSV、Markdown 与 TXT。'
              }}
            </p>
            <button
              v-if="canWrite && filters.status === 'active'"
              class="text-link"
              :disabled="!!pending"
              @click="open('create')"
            >
              上传一份资料<AppIcon name="arrow-right" />
            </button>
          </div>
          <ul v-else class="dc-documents">
            <li v-for="d in documents" :key="d.id">
              <button
                class="dc-document"
                :class="{ selected: selected?.id === d.id }"
                :aria-pressed="selected?.id === d.id"
                :disabled="locked"
                @click="choose(d.id)"
              >
                <span class="dc-file-icon"><AppIcon name="file-text" /></span
                ><span class="dc-document-copy"
                  ><strong>{{ d.title }}</strong
                  ><span
                    >{{ documentCategory(d.category) }}<i>·</i
                    >{{ d.visibility === 'private' ? '私有资料' : '店铺可见' }}<i>·</i
                    >{{ when(d.updated_at) }}</span
                  ></span
                ><AppIcon name="chevron-right" />
              </button>
            </li>
          </ul>
          <footer v-if="cursor" class="dc-list-footer">
            <button class="text-link" :disabled="loading" @click="library.loadList(true)">
              {{ loading ? '正在载入…' : '加载更多资料' }}
            </button>
          </footer>
        </section>
        <aside
          ref="detailPane"
          class="dc-detail"
          tabindex="-1"
          aria-label="资料详情"
          :aria-busy="detailLoading"
        >
          <div v-if="!selected && !detailError" class="dc-detail-empty">
            <span class="dc-file-icon"><AppIcon name="file-text" /></span>
            <h2>{{ detailLoading ? '正在读取资料…' : '每一份原件，都有来处。' }}</h2>
            <p>选择左侧资料，查看原件、版本和使用范围。</p>
          </div>
          <template v-if="selected">
            <div class="dc-detail-kicker">
              <span>{{ documentCategory(selected.category) }}</span
              ><span class="dc-badge">{{
                selected.status === 'archived' ? '已归档' : '原件已保存'
              }}</span>
            </div>
            <h2 class="dc-detail-title">{{ selected.title }}</h2>
            <p class="dc-meta">
              {{
                selected.owner_principal_id === session.principal_id ? '由我上传' : '由其他成员上传'
              }}
              · {{ when(selected.created_at) }}
            </p>
            <div class="dc-visibility">
              <AppIcon name="lock-keyhole" /><span>{{
                selected.visibility === 'private'
                  ? '私有资料，只有所有者可以读取原件。'
                  : '有本店铺访问权限的成员可以读取原件。'
              }}</span>
            </div>
            <div
              v-if="selected.sku_ids?.length || selected.supplier_ids?.length"
              class="dc-associations"
            >
              <span v-for="id in selected.sku_ids" :key="id">{{
                products.find((p) => p.sku_id === id)?.name || id
              }}</span
              ><span v-for="id in selected.supplier_ids" :key="id">{{ id }}</span>
            </div>
            <div v-if="library.canManage(selected)" class="dc-actions">
              <button
                v-if="selected.status === 'active'"
                class="secondary"
                :disabled="locked || !!pending || !!detailError"
                @click="open('append')"
              >
                <AppIcon name="plus" />新版本
              </button>
              <button class="text-link" :disabled="locked || !!pending" @click="open('edit')">
                编辑信息
              </button>
              <button
                class="text-link"
                :disabled="locked || !!pending"
                @click="open(selected.status === 'active' ? 'archive' : 'restore')"
              >
                {{ selected.status === 'active' ? '归档' : '恢复资料' }}
              </button>
            </div>
            <div v-if="selected.status === 'archived'" class="dc-explanation">
              <h3>已收进归档</h3>
              <p>原件和历史版本保留。恢复资料后，才可查看版本及下载原件。</p>
            </div>
            <div v-else-if="!library.canRead(selected)" class="dc-explanation">
              <h3>仅可查看资料信息</h3>
              <p>这是其他成员的私有资料。当前身份不能查看原件、版本或修改资料。</p>
            </div>
            <section v-else class="dc-versions" aria-label="历史版本">
              <header class="dc-section-head">
                <h3>原件与版本</h3>
                <span v-if="detailLoading" role="status">正在读取…</span>
              </header>
              <article v-for="v in versions" :key="v.id" class="dc-version">
                <div class="dc-version-heading">
                  <b>v{{ v.version_no }}</b
                  ><span v-if="v.id === selected.latest_version_id" class="dc-badge">最近上传</span
                  ><span class="dc-meta">{{ fileSize(v.size_bytes) }}</span>
                </div>
                <p class="dc-filename">{{ v.original_name }}</p>
                <p class="dc-meta">{{ when(v.created_at) }}</p>
                <button
                  class="text-link dc-download"
                  :disabled="!!downloading"
                  :aria-label="`下载原件 v${v.version_no} ${v.original_name}`"
                  @click="library.download(v)"
                >
                  <AppIcon name="download" />{{ downloading === v.id ? '正在下载…' : '下载原件' }}
                </button>
                <details class="dc-source">
                  <summary>有效期与原件校验信息</summary>
                  <dl>
                    <dt>生效时间</dt>
                    <dd>{{ v.valid_from ? when(v.valid_from) : '未指定' }}</dd>
                    <dt>失效时间</dt>
                    <dd>{{ v.valid_until ? when(v.valid_until) : '未指定' }}</dd>
                    <dt>SHA-256</dt>
                    <dd class="dc-hash">{{ v.content_sha256 }}</dd>
                  </dl>
                </details>
              </article>
              <p v-if="!versions.length && !detailLoading && !detailError">没有可读取的版本。</p>
              <button
                v-if="versionCursor"
                class="text-link"
                :disabled="detailLoading"
                @click="library.moreVersions()"
              >
                加载更早版本
              </button>
            </section>
          </template>
          <div v-if="detailError" class="notice amber" role="alert">
            <p>{{ detailError }}</p>
            <button v-if="selected" class="text-link" @click="library.select(selected.id)">
              重新读取详情
            </button>
          </div>
        </aside>
      </div>
    </template>
    <AppDialog :open="!!mode" :title="dialogTitle" :busy="locked" @close="mode = ''">
      <form class="dc-form" @submit.prevent="submit">
        <p v-if="mode === 'append'">
          为「{{ selected?.title }}」保存一份新原件。旧版本会完整保留。
        </p>
        <p v-if="mode === 'archive'">
          「{{ selected?.title }}」将移入归档。原件与历史版本保留，归档期间不能下载；随时可以恢复。
        </p>
        <p v-if="mode === 'restore'">
          恢复「{{ selected?.title }}」后，有权限的成员可重新查看版本和下载原件。
        </p>
        <fieldset :disabled="locked || !!pending">
          <label v-if="fileMode" class="dc-upload"
            ><span class="dc-file-icon"><AppIcon name="file-text" /></span
            ><strong>{{ upload?.name || '选择一份原件' }}</strong
            ><span>{{
              upload ? fileSize(upload.size) : 'PDF · DOCX · XLSX · CSV · MD · TXT，最大20 MiB'
            }}</span>
            <span class="dc-upload-action" aria-hidden="true">{{
              upload ? '更换文件' : '浏览文件'
            }}</span>
            <input
              type="file"
              accept=".pdf,.docx,.xlsx,.csv,.md,.txt"
              :required="fileMode"
              aria-label="选择原件"
              @change="picked($event)"
          /></label>
          <template v-if="metaMode">
            <label class="dc-field"
              >资料标题<input v-model="form.title" required maxlength="300" autocomplete="off"
            /></label>
            <div class="dc-form-pair">
              <label class="dc-field"
                >分类<select v-model="form.category" required>
                  <option v-for="value in categoryOptions" :key="value" :value="value">
                    {{ documentCategory(value) }}
                  </option>
                </select></label
              >
              <label class="dc-field"
                >可见范围<select v-model="form.visibility">
                  <option value="store">店铺成员可见</option>
                  <option value="private">仅自己可读</option>
                </select></label
              >
            </div>
            <p class="dc-meta">
              {{
                form.visibility === 'private'
                  ? '其他成员不能读取原件。管理员仍可能查看标题等资料信息。'
                  : '有本店铺访问权限的成员可读取原件，请确认文件适合共享。'
              }}
            </p>
            <details class="dc-relations">
              <summary>关联商品与供应商（可选）</summary>
              <div class="dc-checks">
                <span>商品</span
                ><label v-for="p in products" :key="p.sku_id"
                  ><input v-model="form.sku_ids" type="checkbox" :value="p.sku_id" />{{
                    p.name
                  }}</label
                ><label
                  v-for="id in form.sku_ids.filter((id) => !products.some((p) => p.sku_id === id))"
                  :key="id"
                  ><input v-model="form.sku_ids" type="checkbox" :value="id" />{{ id }}</label
                ><span>供应商</span
                ><label v-for="id in [...new Set([...suppliers, ...form.supplier_ids])]" :key="id"
                  ><input v-model="form.supplier_ids" type="checkbox" :value="id" />{{ id }}</label
                >
              </div>
            </details>
          </template>
          <details v-if="fileMode" class="dc-validity">
            <summary>原件有效期（可选）</summary>
            <p class="dc-meta">按当前设备时区填写，留空表示未指定。</p>
            <div class="dc-form-pair">
              <label class="dc-field"
                >生效时间<input v-model="form.valid_from" type="datetime-local" /></label
              ><label class="dc-field"
                >失效时间<input v-model="form.valid_until" type="datetime-local"
              /></label>
            </div>
          </details>
        </fieldset>
        <p v-if="formError || pendingError" class="notice amber" role="alert">
          {{ formError || pendingError }}
        </p>
        <p v-if="pending && !busy" class="dc-meta">
          结果尚未确认。重试将核实原提交，不会另建一份。
        </p>
        <div class="dc-form-actions">
          <button type="button" class="secondary" :disabled="locked" @click="mode = ''">
            {{ pending ? '稍后核实' : '取消' }}</button
          ><button
            v-if="pendingError && !pending && mode !== 'create'"
            type="button"
            class="secondary"
            @click="reloadForm"
          >
            载入最新资料</button
          ><button type="submit" class="primary" :disabled="locked">
            {{
              locked
                ? '正在保存…'
                : pending
                  ? '重试原提交'
                  : mode === 'archive'
                    ? '确认归档'
                    : mode === 'restore'
                      ? '恢复资料'
                      : fileMode
                        ? '保存原件'
                        : '保存信息'
            }}
          </button>
        </div>
      </form>
    </AppDialog>
  </section>
</template>

<style scoped>
.document-center {
  padding-bottom: 50px;
}
.dc-back {
  margin: 2px 0 26px;
}
.dc-back .icon {
  transform: rotate(180deg);
}
.dc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}
.dc-header h1 {
  margin: 9px 0 14px;
  font-size: clamp(30px, 3.5vw, 48px);
  letter-spacing: -1.6px;
}
.dc-header p {
  max-width: 600px;
}
.dc-header > button {
  flex-shrink: 0;
}
.dc-scope {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 24px 0 32px;
  color: var(--muted);
  font-size: 13px;
}
.dc-scope .icon {
  flex-shrink: 0;
  color: #687f78;
}
.dc-notice {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 20px;
  color: #306a53;
}
.dc-notice span {
  flex: 1;
}
.dc-filters {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 22px;
}
.dc-filters label {
  display: grid;
  gap: 6px;
  min-width: 130px;
}
.dc-label {
  font-size: 12px;
  color: var(--muted);
}
.dc-search {
  flex: 1;
  min-width: 230px !important;
}
.dc-search > div {
  display: flex;
  gap: 10px;
  align-items: center;
  background: rgb(255 255 255 / 55%);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0 14px;
}
.dc-search input {
  width: 100%;
  border: 0;
  background: transparent;
  padding: 11px 0;
  min-width: 0;
}
.dc-filters select,
.dc-field input,
.dc-field select {
  min-height: 46px;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px 12px;
  background: rgb(255 255 255 / 75%);
  color: inherit;
  width: 100%;
  min-width: 0;
}
.dc-extra-filters {
  flex-basis: 100%;
}
summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--muted);
  padding: 6px 0;
}
.dc-filter-entities {
  display: flex;
  gap: 14px;
  padding-top: 10px;
}
.dc-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(0, 0.88fr);
  gap: 36px;
  align-items: start;
}
.dc-library {
  border-radius: 24px;
  overflow: hidden;
  padding: 8px 24px;
}
.dc-section-head {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 70px;
  border-bottom: 1px solid var(--line);
}
.dc-section-head h2 {
  font-size: 18px;
  letter-spacing: -0.4px;
  margin-right: auto;
}
.dc-section-head > span {
  color: var(--muted);
  font-size: 12px;
}
.dc-documents {
  list-style: none;
  margin: 0;
  padding: 0;
}
.dc-documents li + li {
  border-top: 1px solid var(--line);
}
.dc-document {
  width: 100%;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 24px 10px;
  border-radius: 12px;
  transition: background 0.18s;
}
.dc-document:hover {
  background: rgb(255 255 255 / 55%);
}
.dc-document.selected {
  background: rgb(219 233 248 / 58%);
}
.dc-file-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 42px;
  height: 50px;
  border: 1px solid rgb(116 143 172 / 18%);
  border-radius: 11px;
  background: linear-gradient(150deg, #fff, #edf2f5);
  color: #617f9e;
  box-shadow: 0 3px 7px rgb(51 74 94 / 4%);
}
.dc-file-icon .icon {
  width: 22px;
  height: 22px;
}
.dc-document-copy {
  flex: 1;
  min-width: 0;
}
.dc-document-copy strong {
  display: block;
  font-size: 16px;
  font-weight: 550;
  overflow-wrap: anywhere;
}
.dc-document-copy > span {
  display: block;
  margin-top: 7px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}
.dc-document-copy i {
  font-style: normal;
  margin: 0 7px;
}
.dc-document > .icon {
  flex-shrink: 0;
  width: 15px;
  color: #8291a0;
}
.dc-list-footer {
  padding: 17px;
  text-align: center;
  border-top: 1px solid var(--line);
}
.dc-empty {
  padding: 50px 20px;
  text-align: center;
  display: grid;
  justify-items: center;
  gap: 14px;
}
.dc-empty > .icon {
  width: 32px;
  height: 32px;
  color: #8b9aa7;
}
.dc-empty p {
  font-size: 13px;
  max-width: 300px;
}
.dc-detail {
  min-width: 0;
  padding: 24px 0 24px 8px;
  scroll-margin-top: 100px;
}
.dc-detail-empty {
  display: grid;
  justify-items: start;
  gap: 20px;
  padding: 42px 18px;
}
.dc-detail-empty h2 {
  font-size: 24px;
}
.dc-detail-empty p {
  font-size: 14px;
}
.dc-detail-kicker {
  display: flex;
  gap: 12px;
  align-items: center;
  color: var(--muted);
  font-size: 13px;
}
.dc-badge {
  background: rgb(229 239 232 / 90%);
  color: #426454;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  white-space: nowrap;
}
.dc-detail-title {
  font-size: 27px;
  margin: 14px 0 10px;
  overflow-wrap: anywhere;
}
.dc-meta {
  color: var(--muted);
  font-size: 12px;
}
.dc-visibility {
  display: flex;
  align-items: start;
  gap: 9px;
  margin: 20px 0 16px;
  font-size: 13px;
  color: var(--muted);
}
.dc-visibility .icon {
  width: 15px;
  flex-shrink: 0;
}
.dc-associations {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--muted);
}
.dc-associations span {
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: 5px;
  overflow-wrap: anywhere;
}
.dc-actions {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin: 22px 0 10px;
}
.dc-versions {
  margin-top: 14px;
}
.dc-version {
  position: relative;
  padding: 22px 0;
  border-bottom: 1px solid var(--line);
}
.dc-version-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dc-version-heading > .dc-meta {
  margin-left: auto;
}
.dc-version-heading b {
  font-size: 15px;
  font-weight: 550;
}
.dc-filename {
  color: inherit;
  margin: 10px 0 2px;
  overflow-wrap: anywhere;
}
.dc-download {
  margin: 12px 0;
}
.dc-source {
  margin-top: 3px;
}
.dc-source dl {
  margin: 10px 0 0;
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: 7px;
  font-size: 12px;
}
.dc-source dt {
  color: var(--muted);
}
.dc-source dd {
  margin: 0;
}
.dc-hash {
  overflow-wrap: anywhere;
  font-family: monospace;
}
.dc-explanation {
  border-top: 1px solid var(--line);
  margin-top: 26px;
  padding-top: 24px;
}
.dc-explanation p {
  margin-top: 8px;
  font-size: 14px;
}
.dc-recovery {
  margin-bottom: 24px;
}
.dc-recovery .dc-field {
  margin: 12px 0;
}
.dc-form {
  display: grid;
  gap: 20px;
}
.dc-form fieldset {
  display: grid;
  gap: 17px;
  padding: 0;
  margin: 0;
  border: 0;
  min-width: 0;
}
.dc-field {
  display: grid;
  gap: 6px;
  font-size: 13px;
  min-width: 0;
}
.dc-upload {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 10px;
  border: 1px dashed #9aafc1;
  border-radius: 17px;
  padding: 24px 16px;
  background: #f3f6f8;
  cursor: pointer;
  text-align: center;
}
.dc-upload strong {
  overflow-wrap: anywhere;
  max-width: 100%;
}
.dc-upload > span:not(.dc-file-icon) {
  font-size: 12px;
  color: var(--muted);
}
.dc-upload input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}
.dc-upload:focus-within {
  outline: 3px solid #3177cb;
  outline-offset: 3px;
}
.dc-upload > .dc-upload-action {
  color: var(--blue);
  font-weight: 550;
  padding-top: 4px;
}
.dc-form-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.dc-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 8px;
}
.dc-checks {
  display: grid;
  gap: 9px;
  font-size: 13px;
  padding: 10px 0;
}
.dc-checks > span {
  color: var(--muted);
  margin-top: 5px;
}
.dc-checks label {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-wrap: anywhere;
}
.dc-checks input {
  width: 17px;
  height: 17px;
}
.dc-validity .dc-form-pair {
  margin-top: 12px;
}
@media (max-width: 960px) {
  .dc-workspace {
    grid-template-columns: 1fr;
    gap: 24px;
  }
  .dc-detail {
    border-top: 1px solid var(--line);
    padding: 26px 4px;
  }
  .dc-detail-empty {
    padding: 8px 0;
  }
}
@media (max-width: 580px) {
  .dc-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 20px;
  }
  .dc-header h1 {
    font-size: 32px;
  }
  .dc-back {
    margin-bottom: 22px;
  }
  .dc-scope {
    align-items: start;
    margin: 22px 0;
  }
  .dc-library {
    padding: 6px 14px;
  }
  .dc-search {
    flex-basis: 100%;
  }
  .dc-filters label {
    min-width: 0;
  }
  .dc-filters > label:not(.dc-search) {
    flex: 1;
  }
  .dc-document {
    padding: 20px 4px;
    gap: 12px;
  }
  .dc-document-copy i {
    margin: 0 4px;
  }
  .dc-document-copy > span {
    font-size: 11px;
  }
  .dc-form-pair {
    grid-template-columns: 1fr;
  }
  .dc-form input,
  .dc-form select,
  .dc-filters input {
    font-size: 16px;
  }
  .dc-filter-entities {
    flex-direction: column;
  }
  .dc-actions {
    gap: 14px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .dc-document {
    transition: none;
  }
}
</style>
