<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import { downloadFile } from '~/utils/quotations'
import { api } from '~/utils/api'
import { resultFile, type ResultFileFormat } from '~/utils/workResultExport'
import { money, when } from '~/utils/presentation'
const props = defineProps<{ result: Schema<'WorkResult'>; demonstration?: boolean }>()
const shop = useShop(),
  saving = ref(false),
  downloadError = ref('')
const scope = () =>
  [shop.s.session?.principal_id, shop.s.session?.roles.join(','), shop.s.storeId].join(':')
const calculation = computed(() => props.result.calculation)
const recommendation = computed(() =>
  calculation.value?.candidates.find((c) => c.id === calculation.value?.recommended_candidate_id),
)
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
      <h3>{{ result.calculation ? tr(result.title) : result.title }}</h3>
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
    <MarkdownMessage
      :content="
        result.calculation
          ? result.content
              .split('\n')
              .map((line) => tr(line))
              .join('\n')
          : result.content
      "
    />
    <div v-if="recommendation" class="simulation-outcome" :aria-label="tr('推荐候选的代价')">
      <div>
        <small>{{ tr('本次推荐数量') }}</small
        ><strong>{{ joinText([tr(recommendation.quantity), tr('件')], ' ') }}</strong>
      </div>
      <div>
        <small>{{ tr('预计支出') }}</small
        ><strong>{{ tr(money(recommendation.spend_minor)) }}</strong>
      </div>
      <div>
        <small>{{ tr('可用现金剩余') }}</small
        ><strong>{{ tr(money(recommendation.cash_after_minor)) }}</strong>
      </div>
      <div>
        <small>{{ tr('按时到货后缺口') }}</small
        ><strong>{{ joinText([tr(recommendation.shortage_qty), tr('件')], ' ') }}</strong>
      </div>
    </div>
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
    <details
      v-if="
        result.assumptions?.length ||
        result.references?.length ||
        result.provenance?.limitations?.length
      "
    >
      <summary>{{ tr('依据与假设') }}</summary>
      <ul>
        <li v-for="(a, i) in result.assumptions" :key="'a' + i">{{ calculation ? tr(a) : a }}</li>
        <li v-for="(r, i) in result.references" :key="'r' + i">
          {{ calculation ? tr(r.label) : r.label
          }}<small>{{ joinText(['·', tr(r.type), '/', tr(r.id)]) }}</small>
        </li>
        <li v-for="(limit, i) in result.provenance?.limitations" :key="'limit' + i">
          {{ calculation ? tr(limit) : limit }}
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
            <th v-for="(c, i) in result.columns" :key="i">{{ calculation ? tr(c) : c }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, i) in result.rows"
            :key="i"
            :class="{
              'recommended-row':
                !!calculation &&
                !!calculation.recommended_candidate_id &&
                calculation.candidates[i]?.id === calculation.recommended_candidate_id,
            }"
          >
            <td v-for="(value, j) in row" :key="j">{{ calculation ? tr(value) : value }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="result.columns?.length" class="source-note table-scroll-hint">
      {{ tr('左右滑动表格可查看全部数量、现金与判断。') }}
    </p>
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
.simulation-outcome {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  padding: 18px 0;
}
.simulation-outcome small,
.simulation-outcome strong {
  display: block;
}
.simulation-outcome strong {
  font-size: 23px;
  margin-top: 6px;
}
.recommended-row {
  background: rgba(66, 112, 88, 0.09);
  font-weight: 600;
}
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
  .simulation-outcome {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
