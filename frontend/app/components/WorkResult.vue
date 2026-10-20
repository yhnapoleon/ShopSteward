<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import type { NextStepTarget } from '~/surfaces/types'
import { contentKey, resultSurface } from '~/surfaces/derive'
import SurfaceRenderer from '~/components/surfaces/SurfaceRenderer.vue'
import { downloadFile } from '~/utils/quotations'
import { api } from '~/utils/api'
import { resultFile, resultTitle, type ResultFileFormat } from '~/utils/workResultExport'
import { money, when } from '~/utils/presentation'
const props = defineProps<{
  result: Schema<'WorkResult'>
  demonstration?: boolean
  /** The host handles NextStep and ClarificationForm events (the item's own result card). */
  interactive?: boolean
  /** Blocks enter one after another; only where the result is in view, never inside a fold. */
  animate?: boolean
}>()
const emit = defineEmits<{ open: [name: NextStepTarget]; submit: [text: string] }>()
const shop = useShop(),
  saving = ref(false),
  downloadError = ref('')
const scope = () =>
  [shop.s.session?.principal_id, shop.s.session?.roles.join(','), shop.s.storeId].join(':')
const calculation = computed(() => props.result.calculation)
// The body as trusted blocks (redesign §9). Quotation results keep the plain layout below.
const surface = computed(() => resultSurface(props.result))
// Keyed by the stored result, so neither a refresh nor a language switch replays the entrance.
const identity = computed(() => contentKey(props.result))
const stale = computed(
  () =>
    calculation.value &&
    (calculation.value.input.state.state_version !== shop.s.dashboard?.state.state_version ||
      Date.parse(calculation.value.valid_until) <= Date.now()),
)
async function download(format: ResultFileFormat = 'txt') {
  if (saving.value) return
  const p = props.result.provenance,
    originalScope = scope()
  downloadError.value = ''
  if (!p) {
    downloadError.value = '结果缺少可核对的标识，请刷新事项后重试。'
    return
  }
  saving.value = true
  try {
    const value = await api<Schema<'WorkResultExport'>>(
      `/api/v1/work-items/${p.work_id}/results/${p.result_id}`,
    )
    if (originalScope !== scope() || props.result.provenance?.result_id !== p.result_id) return
    const file = resultFile(value, format)
    downloadFile(file.name, file.text, file.mime, format !== 'json')
  } catch (e) {
    if (originalScope === scope()) downloadError.value = (e as Error).message
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <section class="work-result">
    <div class="work-card-top">
      <h3>{{ resultTitle(result) }}</h3>
      <button class="text-link" :disabled="saving" @click="download('txt')">
        {{ tr(saving ? '正在读取结果…' : '保存结果') }}
      </button>
    </div>
    <p v-if="downloadError" class="notice amber" role="alert">
      {{ joinText([tr(downloadError), tr('页面中的结果仍保留，可稍后重试。')]) }}
    </p>
    <p v-if="calculation" class="source-note">
      {{
        joinText([
          tr('独立试算 ·'),
          calculation.input.product_name,
          tr('· 金额为人民币元，数量为件'),
        ])
      }}
    </p>
    <p v-if="calculation" class="source-note">
      {{
        joinText([
          tr('本次现金底线'),
          tr(money(calculation.input.policy.cash_floor_minor)),
          tr('；本期需求'),
          tr(calculation.input.remaining_demand),
          tr('件。'),
        ])
      }}
    </p>
    <p v-if="stale" class="notice amber">
      {{ tr('经营数据或依据有效期已变化。这是当时的比较结果，建立委托前请重新试算。') }}
    </p>
    <p v-if="demonstration" class="notice amber">{{ tr('模拟接入结果，仅验证处理流程。') }}</p>
    <p v-if="result.kind === 'forecast'" class="source-note">
      {{ tr('预测分析，包含假设；不是已发生的经营事实。') }}
    </p>
    <SurfaceRenderer
      v-if="surface"
      :surface="surface"
      :identity="identity"
      :interactive="interactive"
      :animate="animate"
      @open="emit('open', $event)"
      @submit="emit('submit', $event)"
    />
    <MarkdownMessage v-else :content="result.content" />
    <p v-if="result.provenance" class="source-note">
      {{
        joinText([
          tr('生成于'),
          tr(when(result.provenance.generated_at)),
          tr('· 业务截至'),
          tr(when(result.provenance.data_as_of)),
        ])
      }}
    </p>
    <template v-if="!surface">
      <details
        v-if="
          result.assumptions?.length ||
          result.references?.length ||
          result.provenance?.limitations?.length
        "
      >
        <summary>{{ tr('依据与假设') }}</summary>
        <ul>
          <li v-for="(a, i) in result.assumptions" :key="'a' + i">{{ a }}</li>
          <li v-for="(r, i) in result.references" :key="'r' + i">
            {{ r.label }}<small>{{ joinText(['·', tr(r.type), '/', r.id]) }}</small>
          </li>
          <li v-for="(limit, i) in result.provenance?.limitations" :key="'limit' + i">
            {{ limit }}
          </li>
        </ul>
      </details>
      <div
        v-if="result.columns?.length"
        class="work-result-table"
        tabindex="0"
        :aria-label="tr('结果表格，可横向滚动')"
      >
        <table>
          <thead>
            <tr>
              <th v-for="(c, i) in result.columns" :key="i">{{ c }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in result.rows" :key="i">
              <td v-for="(value, j) in row" :key="j">{{ value }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="result.columns?.length" class="source-note table-scroll-hint">
        {{ tr('左右滑动表格可查看全部数量、现金与判断。') }}
      </p>
    </template>
    <div class="result-downloads">
      <button
        v-if="result.columns?.length"
        class="text-link"
        :disabled="saving"
        @click="download('csv')"
      >
        {{ tr('下载 CSV（含依据）') }}
      </button>
      <button v-if="calculation" class="text-link" :disabled="saving" @click="download('json')">
        {{ tr('下载原始计算数据') }}
      </button>
    </div>
    <p class="source-note">{{ tr('以上为本次处理结果；采购及到货以关联业务记录为准。') }}</p>
  </section>
</template>
<style scoped>
.result-downloads {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin: 12px 0;
}
.table-scroll-hint {
  display: none;
}
@media (max-width: 700px) {
  .table-scroll-hint {
    display: block;
  }
}
</style>
