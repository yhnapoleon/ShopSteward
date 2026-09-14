<script setup lang="ts">
import { api, query } from '~/utils/api'
import type {
  ForecastCurrent,
  ForecastHistory,
  ForecastMode,
  ForecastModel,
  ForecastReference,
} from '~/types/forecast'

const props = defineProps<{
  storeId: string
  skuId: string
  canManage: boolean
  stateVersion?: number
}>()
const current = ref<ForecastCurrent | null>(null),
  model = ref<ForecastModel | null>(null)
const loading = ref(false),
  saving = ref(false),
  error = ref(''),
  modelError = ref('')
const mode = ref<ForecastMode>('historical_demo'),
  series = ref(''),
  historyJson = ref('')
const observationEnd = ref(''),
  activate = ref(false)
const requested = useState<ForecastReference | null>('forecast-reference', () => null)
const panel = ref<HTMLElement | null>(null)
let generation = 0,
  readVersion = 0
let poll: ReturnType<typeof setInterval> | undefined
const forecast = computed(() => current.value?.forecast)
const reason = computed(() =>
  current.value?.reason?.split(':', 1)[0] === 'HISTORICAL_DEMO_ONLY'
    ? '模型推演，仅供参考'
    : current.value?.reason,
)
const referenceId = computed(() =>
  requested.value?.storeId === props.storeId && requested.value?.skuId === props.skuId
    ? requested.value.id
    : '',
)
const referenceChanged = computed(() =>
  Boolean(referenceId.value && !loading.value && referenceId.value !== forecast.value?.forecast_id),
)
const points = computed(() => {
  const rows = forecast.value?.daily_predictions || []
  const max = Math.max(1, ...rows.map((row) => row.quantity))
  return rows.map((row, i) => `${24 + i * 72},${134 - (row.quantity / max) * 110}`).join(' ')
})
function prefix() {
  return `/api/v1/stores/${encodeURIComponent(props.storeId)}/forecast`
}
function accept(value: ForecastCurrent) {
  if (
    value.store_id !== props.storeId ||
    value.sku_id !== props.skuId ||
    (value.forecast &&
      (value.forecast.store_id !== props.storeId || value.forecast.sku_id !== props.skuId))
  )
    throw new Error('预测范围与当前门店或商品不一致，请重新读取。')
  current.value = value
  if (value.model) model.value = value.model
}
async function read() {
  if (!props.storeId || !props.skuId || saving.value) return
  const scope = generation,
    request = ++readVersion
  loading.value = true
  error.value = ''
  try {
    const value = await api<ForecastCurrent>(prefix() + query({ sku_id: props.skuId }))
    if (scope !== generation || request !== readVersion) return
    accept(value)
  } catch (e) {
    if (scope !== generation || request !== readVersion) return
    current.value = null
    error.value = (e as Error).message
  } finally {
    if (scope === generation && request === readVersion) loading.value = false
  }
}
async function loadScope() {
  const scope = ++generation
  if (
    requested.value &&
    (requested.value.storeId !== props.storeId || requested.value.skuId !== props.skuId)
  )
    requested.value = null
  ++readVersion
  current.value = null
  model.value = null
  error.value = ''
  modelError.value = ''
  saving.value = false
  loading.value = false
  series.value = ''
  historyJson.value = ''
  observationEnd.value = ''
  activate.value = false
  mode.value = 'historical_demo'
  if (!props.storeId || !props.skuId) return
  await Promise.allSettled([
    read(),
    (async () => {
      try {
        const value = await api<ForecastModel>(prefix() + '/model')
        if (scope !== generation) return
        model.value = value
      } catch (e) {
        if (scope === generation) modelError.value = (e as Error).message
      }
    })(),
  ])
}
function parseHistory(): ForecastHistory[] {
  let rows: unknown
  try {
    rows = JSON.parse(historyJson.value)
  } catch {
    throw new Error('销售历史必须是有效的 JSON 数组。')
  }
  if (
    !Array.isArray(rows) ||
    rows.length < (model.value?.minimum_history_days || 84) ||
    rows.length > 374
  )
    throw new Error('请导入 84–374 天完整且连续的销售历史。')
  let previous = 0
  for (const row of rows) {
    const time =
      typeof row?.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(row.date)
        ? Date.parse(row.date + 'T00:00:00Z')
        : NaN
    if (
      !Number.isFinite(time) ||
      new Date(time).toISOString().slice(0, 10) !== row.date ||
      (previous && time - previous !== 86400000) ||
      row.complete !== true ||
      typeof row.sold_quantity !== 'number' ||
      !Number.isInteger(row.sold_quantity) ||
      row.sold_quantity < 0 ||
      row.sold_quantity > 1_000_000_000
    )
      throw new Error(
        '每日记录须日期递增且无缺日、销量为 0–1,000,000,000 的整数、complete 为 true；缺失销量不能填为零。',
      )
    previous = time
  }
  if (rows.at(-1).date !== observationEnd.value)
    throw new Error('观察截至日必须等于销售历史最后一天。')
  return rows as ForecastHistory[]
}
async function refreshForecast(reuse = false) {
  if (!props.canManage || saving.value || loading.value) return
  const scope = generation
  error.value = ''
  try {
    if (!reuse && !series.value) throw new Error('请选择模型参考系列。')
    const body = reuse
      ? {
          sku_id: props.skuId,
          activate_for_planning:
            current.value?.mode === 'observed' && current.value.activate_for_planning,
        }
      : {
          sku_id: props.skuId,
          series_id: series.value,
          mode: mode.value,
          activate_for_planning: mode.value === 'observed' && activate.value,
          ...(mode.value === 'observed'
            ? { history: parseHistory(), observation_end_date: observationEnd.value }
            : {}),
        }
    saving.value = true
    ++readVersion
    const value = await api<ForecastCurrent>(prefix() + '/refresh', 'POST', body)
    if (scope !== generation) return
    accept(value)
  } catch (e) {
    if (scope === generation) error.value = (e as Error).message
  } finally {
    if (scope === generation) saving.value = false
  }
}
watch(() => [props.storeId, props.skuId], loadScope, { immediate: true })
watch(mode, () => {
  activate.value = false
})
watch(
  () => props.stateVersion,
  () => {
    void read()
  },
)
watch(
  () => requested.value?.nonce,
  async () => {
    if (!referenceId.value) return
    await read()
    await nextTick()
    panel.value?.focus({ preventScroll: true })
    panel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  },
)
onMounted(() => {
  poll = setInterval(() => {
    if (!loading.value) void read()
  }, 30000)
})
onUnmounted(() => {
  generation++
  readVersion++
  if (poll) clearInterval(poll)
})
</script>

<template>
  <section
    ref="panel"
    class="forecast-panel glass"
    role="region"
    aria-label="七日需求预测"
    tabindex="-1"
  >
    <div class="forecast-header">
      <div>
        <div class="eyebrow">SHOPSTEWARD V6</div>
        <h2>七日需求预测</h2>
      </div>
      <span class="tag" :class="{ amber: current?.status !== 'READY' }" role="status">{{
        loading ? '正在读取…' : current?.status || 'UNAVAILABLE'
      }}</span>
    </div>
    <p class="source-note">当前门店 {{ storeId }} · 商品 {{ skuId }}</p>
    <p v-if="error" class="notice amber" role="alert">{{ error }}</p>
    <p v-if="referenceId" class="source-note">正在核对引用：{{ referenceId }}</p>
    <p v-if="referenceChanged" class="notice amber" role="alert">
      该引用已被更新或当前不可用。下方仅展示当前保存的预测，不能作为原引用的复核结果。
    </p>
    <p v-if="reason" class="notice amber">{{ reason }}</p>
    <p v-if="current?.status === 'STALE'" class="notice amber">
      预测已失效，仅供追溯；重新运行并核对适用范围后才能作为当前依据。
    </p>
    <template v-if="forecast">
      <div class="forecast-summary">
        <div>
          <span>七日需求合计</span
          ><strong data-testid="forecast-total">{{ forecast.predicted_quantity }} 件</strong
          ><small>原始合计 {{ forecast.total_quantity_raw.toFixed(2) }} 件，整周向上取整一次</small>
        </div>
        <div>
          <span>来源</span
          ><b>{{
            current?.mode === 'historical_demo' ? '模型推演，仅供参考' : '用户导入的完整销售记录'
          }}</b
          ><small>输入与日期详见可追溯依据</small>
        </div>
      </div>
      <p v-if="current?.mode === 'historical_demo'" class="notice">模型推演，仅供参考。</p>
      <p v-else class="source-note">
        {{
          current?.usable_for_planning
            ? '已明确启用且当前符合规划适用条件。'
            : current?.activate_for_planning
              ? '已启用规划，但当前不符合适用条件；需核对业务时点、有效期与输入状态。'
              : '当前未作为规划依据；还需显式启用并满足业务时点和有效期条件。'
        }}预测是需求估计，采购数量仍须结合库存、在途、现金与逐笔审批。
      </p>
      <figure class="forecast-chart">
        <svg viewBox="0 0 480 160" role="img" aria-label="七日需求预测曲线，具体日期和数量见下表">
          <path d="M24 16V140H466" fill="none" stroke="#b8c5bd" />
          <polyline
            :points="points"
            fill="none"
            stroke="#287b58"
            stroke-width="3"
            stroke-linejoin="round"
          />
        </svg>
        <figcaption>七日需求 · 单位：件</figcaption>
      </figure>
      <div class="forecast-table">
        <table aria-label="七日逐日预测">
          <thead>
            <tr>
              <th scope="col">预测日期</th>
              <th scope="col">预计销量（件）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in forecast.daily_predictions" :key="row.date">
              <th scope="row">{{ row.date.slice(5, 10) }}</th>
              <td>{{ row.quantity.toFixed(2) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <details>
        <summary>版本与可追溯依据</summary>
        <p>观察截至 {{ forecast.observation_end_date }}</p>
        <p>
          预测范围 {{ forecast.horizon_start.slice(0, 10) }} 至
          {{ forecast.horizon_end.slice(0, 10) }}
        </p>
        <p>模型 {{ forecast.model_version }} · 系列 {{ forecast.series_id }}</p>
        <p>生成于 {{ forecast.generated_at }} · 有效至 {{ forecast.valid_until }}</p>
        <p class="long-id">预测编号：{{ forecast.forecast_id }}</p>
        <p v-for="assumption in forecast.assumptions" :key="assumption">{{ assumption }}</p>
      </details>
    </template>
    <p v-else-if="!loading" class="channel-note">暂无可展示的预测。没有数据时不显示零需求。</p>
    <p class="forecast-quality">
      质量说明：v6 历史八周 WAPE 为 34.976%，相对 v5 仅改善
      0.57%；额外四周验证略差。有限历史评估不保证新门店效果，预测不是销量承诺或采购建议。
    </p>
    <details v-if="canManage" open class="forecast-inputs">
      <summary>运行预测</summary>
      <p v-if="modelError" class="notice amber">模型信息暂不可用：{{ modelError }}</p>
      <label class="field-label" for="forecast-mode">输入来源</label
      ><select id="forecast-mode" v-model="mode" class="text-field" :disabled="saving">
        <option value="historical_demo">模型推演，仅供参考</option>
        <option value="observed">导入当前商品销售历史</option>
      </select>
      <label class="field-label" for="forecast-series">模型参考系列</label
      ><select
        id="forecast-series"
        v-model="series"
        class="text-field"
        :disabled="saving || !model"
      >
        <option value="">选择一个已支持的系列</option>
        <option
          v-for="item in model?.supported_series || []"
          :key="item.series_id"
          :value="item.series_id"
        >
          {{ item.series_id }} · {{ item.store_id }} / {{ item.item_id }}
        </option>
      </select>
      <p class="source-note">
        参考系列是模型分类映射；导入记录须来自当前门店商品。支持
        {{ model?.minimum_history_days ?? 84 }}–374 天，建议
        {{ model?.recommended_history_days ?? 374 }} 天。
      </p>
      <template v-if="mode === 'observed'"
        ><label class="field-label" for="forecast-history">完整销售历史 JSON</label
        ><textarea
          id="forecast-history"
          v-model="historyJson"
          class="text-field"
          rows="6"
          :disabled="saving"
          placeholder='[{"date":"2026-01-01","sold_quantity":3,"complete":true}, …]'
        /><label class="field-label" for="forecast-end">观察截至日</label
        ><input
          id="forecast-end"
          v-model="observationEnd"
          type="date"
          class="text-field"
          :disabled="saving"
        />
        <p class="source-note">
          每天一条、日期连续且销量完整。只记录实际已观察销量，缺记录不补零。
        </p>
        <label class="forecast-activate"
          ><input
            v-model="activate"
            type="checkbox"
            :disabled="saving"
          />明确启用这份观测预测作为规划依据（仅在业务时点匹配时生效）</label
        ></template
      >
      <div class="forecast-actions">
        <button class="primary" :disabled="saving || loading || !model" @click="refreshForecast()">
          {{
            saving ? '正在运行…' : mode === 'historical_demo' ? '运行模型推演' : '导入并运行预测'
          }}</button
        ><button
          v-if="current?.forecast"
          class="secondary"
          :disabled="saving || loading"
          @click="refreshForecast(true)"
        >
          复用已保存输入运行{{
            current?.activate_for_planning ? '（保持规划启用）' : '（保持规划关闭）'
          }}
        </button>
      </div>
    </details>
    <p v-else class="channel-note">当前身份可查看预测；运行或导入需要操作员权限。</p>
    <button class="text-link" :disabled="loading || saving" @click="read">
      重新读取已保存预测
    </button>
  </section>
</template>

<style scoped>
.forecast-panel {
  padding: 24px;
  margin-top: 24px;
  scroll-margin-top: 24px;
  min-width: 0;
}
.forecast-header,
.forecast-summary {
  display: flex;
  justify-content: space-between;
  gap: 20px;
}
.forecast-header h2 {
  margin: 6px 0;
}
.forecast-summary {
  margin: 20px 0;
  flex-wrap: wrap;
}
.forecast-summary > div {
  display: grid;
  gap: 6px;
}
.forecast-summary strong {
  font-size: 30px;
}
.forecast-summary small,
.forecast-chart figcaption {
  color: #637168;
  font-size: 12px;
}
.forecast-chart {
  margin: 12px 0;
}
.forecast-chart svg {
  width: 100%;
  max-height: 200px;
}
.forecast-table table {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
}
.forecast-table th,
.forecast-table td {
  padding: 8px;
  text-align: left;
  border-bottom: 1px solid #dce3dd;
}
.forecast-table td {
  text-align: right;
}
.forecast-quality {
  font-size: 12px;
  line-height: 1.7;
  color: #68766e;
  margin-top: 20px;
}
.forecast-inputs {
  border-top: 1px solid #dce3dd;
  padding-top: 16px;
  margin-top: 16px;
}
.forecast-activate {
  display: flex;
  gap: 10px;
  margin: 16px 0;
  align-items: flex-start;
  font-size: 13px;
}
.forecast-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: 16px 0;
}
.long-id,
.source-note {
  overflow-wrap: anywhere;
}
.forecast-panel textarea {
  font-family: monospace;
  resize: vertical;
}
.forecast-panel summary {
  cursor: pointer;
}
</style>
