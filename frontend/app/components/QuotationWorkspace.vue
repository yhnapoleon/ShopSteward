<script setup lang="ts">
import { t as tr, joinText } from '~/i18n'
import { api } from '~/utils/api'
import { when } from '~/utils/presentation'
import type { QuotationFile, QuotationResult, QuotationRule } from '~/utils/quotationApi'
const work = useWorkItems()
const inputId = useId()
const emit = defineEmits<{ changed: [] }>()
const files = ref<QuotationFile[]>([]),
  results = ref<QuotationResult[]>([])
const rule = ref<QuotationRule | null>(null),
  ruleVersion = ref(0)
const selectedFile = ref(''),
  selectedResult = ref(''),
  error = ref(''),
  loading = ref(false)
const sort = ref<'unit_price' | 'source'>('unit_price'),
  record = ref(1),
  field = ref('每包装件数'),
  value = ref('')
const fields = [
  '商品',
  '报价金额',
  '币种',
  '计价单位',
  '每包装件数',
  '最低订购量',
  'MOQ单位',
  '来源',
]
const file = computed(() => files.value.find((f) => f.id === selectedFile.value))
const versions = computed(() =>
  results.value
    .filter((r) => r.file_id === selectedFile.value)
    .sort((a, b) => b.version - a.version),
)
const result = computed(
  () => versions.value.find((r) => r.id === selectedResult.value) || versions.value[0],
)
const ruleSource = (saved: QuotationRule) =>
  [saved.source.confirmation, saved.source.correction_content]
    .filter((value) => typeof value === 'string')
    .join(' · ')
const disabled = computed(
  () => loading.value || work.s.busy || !!work.s.pending || work.s.accessRevoked,
)
const base = computed(() => '/api/v1/work-items/' + work.s.selected)
let request = 0
async function refresh() {
  const id = work.s.selected,
    epoch = work.s.epoch,
    sequence = ++request
  if (!id || work.s.accessRevoked) return
  loading.value = true
  try {
    const [f, r, saved] = await Promise.all([
      api<{ items: QuotationFile[] }>(base.value + '/quotation-files'),
      api<{ items: QuotationResult[] }>(base.value + '/quotation-results'),
      api<{ version: number; rule: QuotationRule | null }>(base.value + '/quotation-rule'),
    ])
    if (id !== work.s.selected || epoch !== work.s.epoch || sequence !== request) return
    const previousFiles = new Set(files.value.map((file) => file.id))
    files.value = (f.items || []).sort(
      (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at),
    )
    results.value = r.items || []
    rule.value = saved.rule || null
    ruleVersion.value = saved.version || 0
    const added = files.value.filter((file) => !previousFiles.has(file.id))
    if (added.length || !files.value.some((f) => f.id === selectedFile.value))
      selectedFile.value = added.at(-1)?.id || files.value.at(-1)?.id || ''
    error.value = ''
  } catch (e) {
    if (id === work.s.selected && epoch === work.s.epoch && sequence === request)
      error.value = (e as Error).message
  } finally {
    if (sequence === request) loading.value = false
  }
}
watch(
  () => [work.s.epoch, work.s.selected],
  () => {
    files.value = []
    results.value = []
    rule.value = null
    ruleVersion.value = 0
    selectedFile.value = ''
    selectedResult.value = ''
    error.value = ''
    value.value = ''
  },
)
watch(
  () => [
    work.s.detail?.item.version,
    work.s.detail?.item.updated_at,
    work.s.epoch,
    work.s.selected,
  ],
  refresh,
  { immediate: true },
)
watch(selectedFile, () => {
  selectedResult.value = ''
  value.value = ''
  sort.value = rule.value?.sort_by || 'unit_price'
})
async function process(persist: boolean) {
  if (!file.value || disabled.value) return
  const corrections = [...(result.value?.corrections || [])]
  if (value.value.trim()) {
    const old = corrections.findIndex((c) => c.record === record.value && c.field === field.value)
    if (old >= 0) corrections.splice(old, 1)
    corrections.push({ record: record.value, field: field.value, value: value.value.trim() })
  }
  const correctionContent = value.value.trim()
    ? tr('第 {0} 条资料：{1} = {2}', [record.value, field.value, value.value.trim()])
    : tr(
        sort.value === 'unit_price'
          ? '按单件价排序，保留原始来源与缺失字段。'
          : '按来源排序，保留原始来源与缺失字段。',
      )
  const d = await work.quotation('quotation-results', {
    file_id: file.value.id,
    base_result_id: result.value?.id,
    corrections,
    sort_by: sort.value,
    persist_rule: persist,
    expected_rule_version: ruleVersion.value,
    correction_content: correctionContent,
  })
  if (d) {
    selectedResult.value = ''
    value.value = ''
    await refresh()
    emit('changed')
  }
}
async function removeRule() {
  const d = await work.quotation('quotation-rule', {
    expected_rule_version: ruleVersion.value,
    operation: 'remove',
    correction_content: tr('取消长期报价规则'),
  })
  if (d) {
    await refresh()
    emit('changed')
  }
}
</script>
<template>
  <section
    v-if="files.length || work.s.detail?.item.result?.kind === 'quotation'"
    class="glass work-status-panel quotation-workspace"
  >
    <h2>{{ tr('报价原件与结果') }}</h2>
    <p v-if="error" class="notice amber" role="alert">
      {{ tr(error) }} <button class="text-link" @click="refresh">{{ tr('重新同步') }}</button>
    </p>
    <label :for="inputId + '-file'">{{ tr('报价原件') }}</label>
    <select :id="inputId + '-file'" v-model="selectedFile" :disabled="disabled">
      <option v-for="f in files" :key="f.id" :value="f.id">{{ f.filename }}</option>
    </select>
    <p v-if="file" class="source-note">
      {{ joinText([file.filename, tr('· 上传于'), tr(when(file.created_at))]) }}
      <a
        class="text-link"
        :href="'/api/backend' + base + '/quotation-files/' + file.id + '/download'"
        download
        >{{ tr('下载原件') }}</a
      >
    </p>
    <details v-if="file" class="knowledge-note">
      <summary>{{ tr('原件校验信息') }}</summary>
      <p class="source-note quotation-hash">SHA-256: {{ file.sha256 }}</p>
    </details>
    <div v-if="versions.length">
      <label :for="inputId + '-version'">{{ tr('结果版本') }}</label>
      <select :id="inputId + '-version'" v-model="selectedResult" :disabled="disabled">
        <option value="">{{ tr('最新结果') }}</option>
        <option v-for="r in versions" :key="r.id" :value="r.id">
          {{ tr('版本 {0} · {1}', [r.version, when(r.created_at)]) }}
        </option>
      </select>
    </div>
    <template v-if="result">
      <p
        v-if="
          ['RECEIVED', 'PROCESSING', 'WAITING_INPUT'].includes(work.s.detail?.item.status || '')
        "
        class="notice"
      >
        {{ tr('这是已保存的报价版本；新要求尚未完成时请先核对更新状态。') }}
      </p>
      <p class="source-note">{{ tr('服务器结果 · 版本 {0}', [result.version]) }}</p>
      <div v-if="result.issues.length" class="notice amber">
        <b>{{ tr('缺失或不能确定的内容') }}</b>
        <ul>
          <li v-for="issue in result.issues" :key="issue">{{ issue }}</li>
        </ul>
        <p>{{ tr('已知结果保留，缺失字段不猜测、不当成0。') }}</p>
      </div>
      <div class="work-result-table" tabindex="0" :aria-label="tr('报价结果表格')">
        <table>
          <thead>
            <tr>
              <th>{{ tr('资料行') }}</th>
              <th>{{ tr('商品') }}</th>
              <th>{{ tr('单件价') }}</th>
              <th>{{ tr('最低订购量') }}</th>
              <th>{{ tr('原报价') }}</th>
              <th>{{ tr('来源') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in result.rows" :key="r.record">
              <td>{{ r.record }}</td>
              <td>{{ r.product }}</td>
              <td>
                {{ r.unit_price === null ? tr('暂不能计算') : r.unit_price + ' CNY'
                }}<small>{{ r.basis }}</small>
              </td>
              <td>
                {{ r.moq ?? tr('未提供') }} {{ r.moq_unit
                }}<small>{{
                  r.moq_pieces === null ? tr('折算件数暂缺') : tr('折合 {0} 件', [r.moq_pieces])
                }}</small>
              </td>
              <td>
                {{ r.price ?? tr('未提供') }} {{ r.currency }} / {{ r.unit
                }}<small>{{ tr('包装件数') }}: {{ r.pack ?? tr('未提供') }}</small>
              </td>
              <td>{{ r.source || tr('未提供') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="result.rule" class="notice">
        {{
          result.sort_by === result.rule.sort_by
            ? tr('本次应用规则 v{0}，来源：{1}', [result.rule.version, ruleSource(result.rule)])
            : tr('此版本使用临时排序，引用当时的规则 v{0}。', [result.rule.version])
        }}
      </p>
      <a
        class="text-link"
        :href="'/api/backend' + base + '/quotation-results/' + result.id + '/download'"
        download
        >{{ tr('下载此版本 CSV') }}</a
      >
    </template>
    <p v-else-if="file" class="notice">
      {{ tr('原件已保存，尚未生成计算结果。可以直接整理，也可以在对话里补充要求。') }}
    </p>
    <fieldset v-if="file" :disabled="disabled" class="quotation-correction">
      <legend>{{ tr('补充或纠正这份资料') }}</legend>
      <p class="source-note">
        {{ tr('填写需要纠正的字段；留空则沿用当前版本。也可以直接在右侧对话说明。') }}
      </p>
      <div class="quotation-fields">
        <label
          >{{ tr('资料行') }}<input v-model.number="record" type="number" min="1" step="1"
        /></label>
        <div>
          <label :for="inputId + '-field'">{{ tr('字段') }}</label>
          <select :id="inputId + '-field'" v-model="field">
            <option v-for="f in fields" :key="f" :value="f">{{ tr(f) }}</option>
          </select>
        </div>
        <label>{{ tr('正确值') }}<input v-model="value" maxlength="1000" /></label>
      </div>
      <label :for="inputId + '-sort'">{{ tr('整理顺序') }}</label>
      <select :id="inputId + '-sort'" v-model="sort">
        <option value="unit_price">{{ tr('按单件价排序') }}</option>
        <option value="source">{{ tr('按来源排序') }}</option>
      </select>
      <div class="demo-actions">
        <button class="primary" @click="process(false)">{{ tr('仅更新本次结果') }}</button>
        <button class="secondary" @click="process(true)">{{ tr('更新并记住整理顺序') }}</button>
      </div>
      <p class="source-note">
        {{
          tr(
            '字段补充只适用于这份原件；长期保存的整理顺序会用于你在本店的新报价事项。旧结果保持原版本。',
          )
        }}
      </p>
    </fieldset>
    <details v-if="rule" class="knowledge-note">
      <summary>{{ tr('已保存的报价整理规则') }}</summary>
      <p>
        {{
          tr('规则 v{0} · {1}', [
            rule.version,
            tr(rule.sort_by === 'unit_price' ? '按单件价排序' : '按来源排序'),
          ])
        }}
      </p>
      <p>{{ tr('来源：') }}{{ ruleSource(rule) }}</p>
      <NuxtLink
        v-if="typeof rule.source.work_id === 'string'"
        class="text-link"
        :to="{
          query: { view: 'work', item: rule.source.work_id, store: work.s.detail?.item.store_id },
        }"
        >{{ tr('查看规则来源事项') }}</NuxtLink
      >
      <button class="text-link" :disabled="disabled" @click="removeRule">
        {{ tr('撤回要求') }}
      </button>
    </details>
    <p v-if="work.s.error" class="notice amber" role="alert">{{ tr(work.s.error) }}</p>
  </section>
</template>
<style scoped>
.quotation-workspace select,
.quotation-workspace input {
  width: 100%;
  min-width: 0;
  min-height: 44px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f8fafc;
  color: inherit;
  font: inherit;
  margin: 6px 0 12px;
}
.quotation-workspace label {
  display: block;
  font-size: 14px;
  color: #42617a;
}
.quotation-workspace select:focus-visible,
.quotation-workspace input:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
}
.quotation-workspace td small {
  display: block;
  margin-top: 5px;
}
.quotation-hash {
  overflow-wrap: anywhere;
}
.quotation-correction {
  border: 1px solid rgba(100, 110, 100, 0.2);
  border-radius: 12px;
  padding: 16px;
  margin-top: 20px;
}
.quotation-fields {
  display: grid;
  grid-template-columns: 70px 1fr 1fr;
  gap: 12px;
}
@media (max-width: 700px) {
  .quotation-fields {
    grid-template-columns: 1fr;
  }
}
</style>
