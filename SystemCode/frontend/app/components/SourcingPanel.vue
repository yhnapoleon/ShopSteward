<script setup lang="ts">
// One reviewer per supplier reads that supplier's documents into an offer card. Code keeps a
// card only when every excerpt it cites is in a document the reviewer opened; the offers that
// pass are compared by the solver above. Nothing here approves or sends a purchase.
import { joinText, t as tr } from '~/i18n'
import { api } from '~/utils/api'
import { money } from '~/utils/presentation'
import type { Schema } from '~/types/models'
import type { RecoveryCase, Sourcing, SupplierReview } from '~/types/recovery'
const props = defineProps<{
  detail: RecoveryCase | null
  storeId: string
  skuId: string
  disabled: boolean
}>()
const emit = defineEmits<{ source: [district: string] }>()
const shop = useShop()
const files = ref<Schema<'SupplierDocumentSet'> | null>(null)
// The district the sample documents are written for; a place name, so it is not translated.
const DISTRICT = '滨江区'
const district = ref(DISTRICT),
  error = ref(''),
  loading = ref(false)
const sourcing = computed(() => (props.detail?.sourcing as Sourcing | null | undefined) || null)
const running = computed(() => sourcing.value?.status === 'running')
const operator = computed(() => shop.hasRole('operator'))
// A supplier the store is already connected to keeps its structured offer; it is not re-read.
const readable = computed(() => (files.value?.suppliers || []).filter((s) => !s.connected))
const kinds: Record<string, string> = {
  quote: '报价单',
  notice: '通知函',
  terms: '合作条款',
  history: '履约记录',
  other: '其他资料',
}
const fields: Record<string, string> = {
  unit_price_minor: '单价',
  minimum_order_quantity: '起订量',
  lead_time_days: '交期',
  valid_until: '有效期',
  status: '不供货的依据',
}
const reasons: Record<string, string> = {
  SKU_NOT_COVERED: '报价单里没有这件商品',
  STORE_NOT_SERVED: '门店不在它的配送范围内',
  SUPPLY_WITHDRAWN: '已发通知暂停供应这件商品',
}
const problems: Record<string, string> = {
  invalid_card: '交回的内容不是一张完整的报价卡',
  wrong_supplier: '交回的报价卡写的是另一家供应商',
  asked_user: '审查者没有读资料，而是反过来提问',
  reviewer_failed: '这位审查者没有完成阅读',
}
const failures: Record<string, string> = {
  SOURCING_INTERRUPTED: '阅读过程被中断，没有得到结果。可以重新寻源。',
  SOURCING_UNAVAILABLE: '审查者暂时不可用，没有得到结果。可以稍后重新寻源。',
  CASE_INPUT_CHANGED: '阅读期间这项事项的要求已修改，读出的报价没有登记。请重新寻源。',
}
const problem = (code: string) =>
  code.startsWith('uncited:')
    ? joinText([tr(fields[code.slice(8)] || code.slice(8)), tr('的引文在资料里找不到')])
    : tr(problems[code] || code)
const verdict = (review: SupplierReview) =>
  !review.card
    ? '两次阅读都没有通过核对，这家不参与比较'
    : review.card.status === 'no_offer'
      ? '读完资料：这家不能供货'
      : sourcing.value?.left_out?.includes(review.supplier_id)
        ? '读出了报价，但只比较最便宜的三家，这家未参与'
        : '读出了报价，已登记并参与比较'
async function load() {
  if (!props.storeId) return
  try {
    files.value = await api<Schema<'SupplierDocumentSet'>>(
      `/api/v1/stores/${encodeURIComponent(props.storeId)}/supplier-documents`,
    )
  } catch (e) {
    error.value = (e as Error).message
  }
}
async function loadSample() {
  error.value = ''
  loading.value = true
  try {
    files.value = await api<Schema<'SupplierDocumentSet'>>(
      `/api/v1/stores/${encodeURIComponent(props.storeId)}/supplier-documents/sample`,
      'POST',
      { sku_id: props.skuId, district: district.value.trim() || DISTRICT },
    )
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => props.storeId, load)
</script>
<template>
  <section class="sourcing-panel" data-sourcing>
    <h3>{{ tr('寻源：每家供应商的资料由一位审查者来读') }}</h3>
    <p class="source-note">
      {{
        tr(
          '审查者只读自己那一家的报价单、通知函和条款，交回一张带引文的报价卡。引文在资料里找不到的卡不采用；通过的报价登记后由上面的试算统一比较。寻源不会批准或发送采购。',
        )
      }}
    </p>
    <div v-if="files && !readable.length" class="sourcing-empty">
      <p>{{ tr('还没有可供阅读的供应商资料。') }}</p>
      <button
        class="secondary"
        type="button"
        :disabled="loading || !operator || !skuId"
        @click="loadSample"
      >
        {{ tr('载入三家供应商的示例资料') }}
      </button>
      <p class="source-note">
        {{ tr('示例资料是为演示编写的，围绕这件商品，含一份已生效的调价通知和一家按箱报价的供应商。') }}
      </p>
    </div>
    <details v-else-if="files" class="sourcing-files">
      <summary>
        {{
          joinText([
            tr('资料在档：'),
            tr(readable.length),
            tr('家供应商，'),
            tr(readable.reduce((total, s) => total + s.documents.length, 0)),
            tr('份资料'),
          ])
        }}
      </summary>
      <div v-for="supplier in readable" :key="supplier.supplier_id" class="sourcing-supplier-files">
        <h4>{{ joinText([supplier.supplier_id, '·', supplier.name]) }}</h4>
        <details v-for="doc in supplier.documents" :key="doc.doc_id">
          <summary>{{ joinText([tr(kinds[doc.kind] || doc.kind), '·', doc.doc_id]) }}</summary>
          <pre>{{ doc.text }}</pre>
        </details>
      </div>
    </details>
    <div v-if="readable.length" class="sourcing-start">
      <label
        >{{ tr('门店所在区域')
        }}<input v-model="district" :disabled="disabled || running" maxlength="64"
      /></label>
      <button
        class="primary"
        type="button"
        :disabled="disabled || running || !detail || !operator"
        @click="emit('source', district.trim() || DISTRICT)"
      >
        {{ tr(running ? '审查者正在读资料…' : sourcing ? '重新寻源' : '开始寻源') }}
      </button>
    </div>
    <p v-if="readable.length && !detail" class="source-note">
      {{ tr('先在上面填写预算并开始分析，建立这项恢复事项后再寻源。') }}
    </p>
    <p v-if="error" role="alert" class="notice amber">{{ tr(error) }}</p>
    <template v-if="sourcing">
      <p class="sourcing-request" role="status">
        {{
          joinText([
            tr('向每位审查者提出的需求：'),
            sourcing.request.sku_id,
            tr('，缺口'),
            tr(sourcing.request.shortfall_qty),
            tr('件，最早缺货日'),
            sourcing.request.short_from || '-',
            tr('，门店在'),
            sourcing.request.district,
          ])
        }}
      </p>
      <p v-if="running" class="notice" role="status">
        {{
          joinText([
            tr('已读完'),
            tr(sourcing.reviews.length),
            '/',
            tr(sourcing.suppliers.length),
            tr('家'),
          ])
        }}
      </p>
      <p v-for="code in sourcing.missing || []" :key="code" class="notice amber" role="alert">
        {{ tr(failures[code] || code) }}
      </p>
      <div class="sourcing-reviews">
        <article
          v-for="review in sourcing.reviews"
          :key="review.supplier_id"
          class="sourcing-review"
          :data-sourcing-review="review.supplier_id"
          :data-accepted="Boolean(review.card)"
        >
          <h4>{{ joinText([review.supplier_id, '·', review.name || '']) }}</h4>
          <p class="sourcing-verdict">{{ tr(verdict(review)) }}</p>
          <template v-if="review.card?.offer">
            <dl>
              <div>
                <dt>{{ tr('单价') }}</dt>
                <dd>{{ tr(money(review.card.offer.unit_price_minor)) }}</dd>
              </div>
              <div>
                <dt>{{ tr('起订量') }}</dt>
                <dd>
                  {{ joinText([tr(review.card.offer.minimum_order_quantity), tr('件')]) }}
                </dd>
              </div>
              <div>
                <dt>{{ tr('装箱') }}</dt>
                <dd>{{ joinText([tr(review.card.offer.pack_size), tr('件/箱')]) }}</dd>
              </div>
              <div>
                <dt>{{ tr('交期') }}</dt>
                <dd>
                  {{
                    review.card.offer.lead_time_days
                      ? joinText([tr(review.card.offer.lead_time_days), tr('天')])
                      : tr('当日送达')
                  }}
                </dd>
              </div>
              <div>
                <dt>{{ tr('有效期') }}</dt>
                <dd>
                  {{ joinText([review.card.offer.valid_from, '~', review.card.offer.valid_until]) }}
                </dd>
              </div>
              <div>
                <dt>{{ tr('报价单号') }}</dt>
                <dd>{{ review.card.offer.offer_version }}</dd>
              </div>
            </dl>
          </template>
          <p v-else-if="review.card" class="notice amber">
            {{ tr(reasons[review.card.reason || ''] || review.card.reason || '') }}
          </p>
          <p v-if="review.card" class="source-note">
            {{
              tr('近期履约 {0} 次，其中迟到 {1} 次', [
                review.card.history.deliveries,
                review.card.history.late,
              ])
            }}
          </p>
          <details v-if="review.card?.citations.length">
            <summary>{{ tr('每一项的出处') }}</summary>
            <ul class="sourcing-citations">
              <li v-for="(citation, index) in review.card.citations" :key="index">
                <b>{{ tr(fields[citation.field] || citation.field) }}</b>
                <small>{{ citation.doc_id }}</small>
                <q>{{ citation.quote }}</q>
              </li>
            </ul>
          </details>
          <details
            v-if="review.attempts.length > 1 || !review.card"
            :open="!review.card"
            class="sourcing-attempts"
          >
            <summary>
              {{ tr('阅读了 {0} 次', [review.attempts.length]) }}
            </summary>
            <div v-for="attempt in review.attempts" :key="attempt.attempt">
              <b>{{
                joinText([
                  tr('第 {0} 次阅读', [attempt.attempt]),
                  '·',
                  tr(attempt.problems.length ? '被退回' : '通过核对'),
                ])
              }}</b>
              <small>{{ joinText([attempt.model, '·', tr('打开了'), attempt.opened.join('、')]) }}</small>
              <ul v-if="attempt.problems.length">
                <li v-for="code in attempt.problems" :key="code">{{ problem(code) }}</li>
              </ul>
              <small v-for="reason in attempt.reasons" :key="reason">{{ reason }}</small>
            </div>
          </details>
        </article>
      </div>
      <p v-if="sourcing.review_bundle" class="source-note">
        {{
          joinText([
            tr('审查者文本版本'),
            sourcing.review_bundle.revision,
            tr('· 解释文本版本'),
            sourcing.explain_bundle || '',
          ])
        }}
      </p>
    </template>
  </section>
</template>
<style scoped>
.sourcing-panel {
  border-top: 1px solid #e2e8e3;
  margin-top: 18px;
  padding-top: 16px;
  display: grid;
  gap: 10px;
}
.sourcing-panel h3,
.sourcing-panel h4 {
  margin: 0;
}
.source-note {
  font-size: 0.85rem;
  color: #607468;
  margin: 0;
}
.sourcing-start {
  display: flex;
  align-items: end;
  gap: 14px;
  flex-wrap: wrap;
}
.sourcing-start label {
  display: grid;
  gap: 6px;
  font-size: 0.9rem;
}
.sourcing-start input {
  border: 1px solid #d4dbd6;
  border-radius: 10px;
  padding: 9px 10px;
  background: #fff;
  color: #203b31;
  width: 160px;
}
.sourcing-panel pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 0.8rem;
  background: #fff;
  border: 1px solid #e2e8e3;
  border-radius: 10px;
  padding: 10px;
  max-height: 320px;
  overflow: auto;
}
.sourcing-supplier-files {
  margin: 10px 0;
}
.sourcing-panel summary {
  cursor: pointer;
  padding: 6px 0;
}
.sourcing-reviews {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 14px;
}
.sourcing-review {
  border: 1px solid #dce6dd;
  border-radius: 14px;
  padding: 14px 16px;
  background: #ffffffa8;
  display: grid;
  gap: 8px;
  align-content: start;
}
.sourcing-review[data-accepted='false'] {
  border-color: #e3c98b;
}
.sourcing-verdict {
  margin: 0;
  font-size: 0.9rem;
}
.sourcing-review dl {
  margin: 0;
}
.sourcing-review dl > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin: 6px 0;
}
.sourcing-review dt {
  color: #607468;
}
.sourcing-review dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.sourcing-citations {
  padding-left: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}
.sourcing-citations small,
.sourcing-attempts small {
  display: block;
  color: #607468;
  overflow-wrap: anywhere;
}
.sourcing-citations q {
  display: block;
  font-size: 0.82rem;
  overflow-wrap: anywhere;
  quotes: none;
  border-left: 3px solid #dce6dd;
  padding-left: 8px;
  white-space: pre-wrap;
}
.sourcing-attempts ul {
  padding-left: 20px;
  margin: 4px 0;
}
.sourcing-panel button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
