<script setup lang="ts">
import { money, when } from '~/utils/presentation'
import type { RecoveryCandidate } from '~/types/recovery'
const props = defineProps<{ missionId: string }>()
const shop = useShop()
const recovery = useRecoveryCase(() => props.missionId)
const { detail, busy, error, syncError, pending, revoked } = recovery
const expanded = ref(false),
  objective = ref('分析供应变化对备货的影响，并比较等待与应急补购。')
const budget = ref(''),
  quantityCap = ref(''),
  demand = ref(''),
  settlement = ref('')
const editing = ref(false),
  validation = ref(''),
  notice = ref('')
const operator = computed(() => shop.hasRole('operator'))
const suppliers = ref<string[]>([])
const availableSuppliers = computed(() => [
  ...new Set(
    (shop.s.catalog?.offers || [])
      .filter((offer) => offer.sku_id === shop.mission.value?.sku_id)
      .map((offer) => offer.supplier_id),
  ),
])
const disabled = computed(() => busy.value || !!pending.value || revoked.value || !operator.value)
const now = ref(Date.now())
const expired = computed(
  () => !!detail.value?.proposal && Date.parse(detail.value.proposal.expires_at) <= now.value,
)
const stale = computed(
  () =>
    editing.value ||
    expired.value ||
    detail.value?.stale ||
    !['OPTIONS_READY'].includes(detail.value?.status || ''),
)
const terminal = computed(() =>
  ['CLOSED', 'CANCELLED', 'RESOLVED'].includes(detail.value?.status || ''),
)
const prepared = computed(
  () =>
    detail.value?.plan_revision === detail.value?.current_revision &&
    detail.value?.plan_status === 'PENDING_APPROVAL',
)
const experts = computed(
  () =>
    detail.value?.expert_analysis as {
      status?: string
      strategy?: string
      subtasks?: {
        subtask_id: string
        role?: string
        status: string
        claims?: { statement: string; support: string[] }[]
        missing?: string[]
      }[]
      merged?: {
        conflicts?: {
          type: string
          resolved_by?: string
          statement?: string
          positions?: { statement: string }[]
        }[]
        clarification?: { question: string } | null
      }
    } | null,
)
const expertRoles: Record<string, string> = {
  evidence: '证据核对',
  impact: '经营影响',
  options: '方案比较',
  single: '综合分析',
  fixed: '固定流程说明',
}
const expertStrategies: Record<string, string> = {
  fixed: '固定流程',
  single: '单 Agent',
  static_multi: '固定三专家',
  adaptive_multi: '按需专家',
}
// Contested or uncited statements were not adopted by the join; say so explicitly.
const expertDisputes = computed(() =>
  (experts.value?.merged?.conflicts || [])
    .filter((conflict) => !conflict.resolved_by)
    .map((conflict) =>
      conflict.type === 'uncited_calculation'
        ? `未引用试算结果的数字，未采信：${conflict.statement}`
        : `专家结论存在分歧，尚未采信：${(conflict.positions || []).map((p) => p.statement).join(' / ')}`,
    ),
)
const expertStatuses: Record<string, string> = {
  disabled: '未启用',
  unavailable: '尚未配置',
  running: '分析中',
  complete: '已完成',
  partial: '部分完成',
  failed: '未完成',
  needs_input: '需要补充',
}
let timer: ReturnType<typeof setInterval> | undefined
let polling = false
onMounted(() => {
  timer = setInterval(async () => {
    now.value = Date.now()
    if (
      expanded.value &&
      detail.value &&
      !busy.value &&
      !pending.value &&
      !revoked.value &&
      !polling
    ) {
      polling = true
      try {
        await recovery.load(detail.value.id)
      } finally {
        polling = false
      }
    }
  }, 5000)
})
onUnmounted(() => clearInterval(timer))
const labels: Record<string, string> = {
  OPEN: '待分析',
  ANALYZING: '分析中',
  NEEDS_INPUT: '需要补充',
  OPTIONS_READY: '方案可比较',
  MONITORING: '跟进中',
  RECHECK_REQUIRED: '依据已变化，需重新分析',
  BLOCKED: '需要处理',
  RESOLVED: '已解决',
  CLOSED: '已结束',
  CANCELLED: '已停止',
}
const reasons: Record<string, string> = {
  BUDGET_EXCEEDED: '超出本次预算',
  CASH_FLOOR_VIOLATION: '低于现金底线',
  OFFER_EXPIRED: '报价已过期',
  UNKNOWN_ACTION: '原采购结果待核实',
  INFEASIBLE: '不满足当前约束',
}
watch(
  () => props.missionId,
  () => {
    expanded.value = false
    editing.value = false
    notice.value = ''
    demand.value = ''
  },
)
watch(
  () => detail.value?.id,
  () => {
    if (detail.value) {
      budget.value = (detail.value.budget_minor / 100).toFixed(2)
      quantityCap.value =
        detail.value.max_purchase_qty == null ? '' : String(detail.value.max_purchase_qty)
      objective.value = detail.value.objective
      suppliers.value = [...(detail.value.supplier_ids || [])]
    }
  },
)
async function toggle() {
  expanded.value = !expanded.value
  if (expanded.value) await recovery.load()
}
function changed() {
  editing.value = true
  notice.value = ''
}
function payload() {
  validation.value = ''
  const amount = budget.value.trim()
  if (!/^\d+(?:\.\d{1,2})?$/.test(amount)) throw Error('预算请输入非负金额，最多两位小数。')
  const [whole, decimal = ''] = amount.split('.')
  const minor = Number(whole) * 100 + Number(decimal.padEnd(2, '0'))
  if (!Number.isSafeInteger(minor) || minor > 1_000_000_000) throw Error('预算金额超出允许范围。')
  const cap = quantityCap.value.trim()
  if (cap && (!/^\d+$/.test(cap) || Number(cap) > 1_000_000))
    throw Error('数量上限请输入 0 至 1000000 的整数；留空表示无额外上限。')
  if (!objective.value.trim()) throw Error('请填写这次需要分析的经营问题。')
  if (
    suppliers.value.length > 3 ||
    (!suppliers.value.length && availableSuppliers.value.length > 3)
  )
    throw Error('请选择一至三家供应商参与本次比较。')
  const body: Record<string, unknown> = {
    objective: objective.value.trim(),
    budget_minor: minor,
    max_purchase_qty: cap ? Number(cap) : null,
    supplier_ids: suppliers.value.length ? [...suppliers.value] : null,
  }
  if (demand.value.trim()) {
    const values = demand.value
      .trim()
      .split(/[,，]/)
      .map((s) => s.trim())
    if (values.length !== 7 || values.some((s) => !/^\d+$/.test(s) || Number(s) > 1_000_000))
      throw Error('七日需求必须填写七个非负整数，使用逗号分隔。')
    const date = new Date(settlement.value + 'Z')
    if (!settlement.value || Number.isNaN(date.getTime()))
      throw Error('请设置首日结算时间（UTC）。')
    body.daily_demand = values.map((s, index) => ({
      settlement_at: new Date(date.getTime() + index * 86400000).toISOString(),
      demand_qty: Number(s),
    }))
  }
  return body
}
async function run() {
  notice.value = ''
  try {
    const body = payload()
    const value = detail.value ? await recovery.revise(body) : await recovery.start(body)
    if (value) editing.value = false
  } catch (e) {
    validation.value = (e as Error).message
  }
}
async function adopt(candidate: RecoveryCandidate) {
  if (stale.value) return
  const value = await recovery.materialize(candidate)
  if (value?.plan_id) {
    notice.value = '恢复方案已生成，采购仍需在原方案卡中确认。'
    await shop.refresh(true)
  }
}
async function retry() {
  const value = await recovery.retry()
  if (value?.plan_id) {
    notice.value = '恢复方案已生成，采购仍需在原方案卡中确认。'
    await shop.refresh(true)
  }
  if (value) editing.value = false
}
async function recheck() {
  const value = await recovery.control('refresh')
  if (value) editing.value = false
}
function newCase() {
  if (!recovery.newDraft()) return
  objective.value = '分析供应变化对备货的影响，并比较等待与应急补购。'
  budget.value = ''
  quantityCap.value = ''
  demand.value = ''
  settlement.value = ''
  suppliers.value = []
  editing.value = false
  validation.value = ''
  notice.value = ''
}
</script>

<template>
  <section class="recovery-workspace glass" aria-label="供应异常应对">
    <button class="text-link recovery-toggle" :aria-expanded="expanded" @click="toggle">
      供应异常应对
    </button>
    <template v-if="expanded">
      <p class="source-note">比较未来七天的缺货、现金和补购方案。分析不会批准或发送采购。</p>
      <div v-if="recovery.items.value.length" class="recovery-history">
        <label
          >已保存的恢复事项
          <select
            :value="detail?.id || ''"
            :disabled="busy || !!pending"
            @change="recovery.load(($event.target as HTMLSelectElement).value)"
          >
            <option v-if="!detail" value="" disabled>正在创建新事项</option>
            <option v-for="item in recovery.items.value" :key="item.id" :value="item.id">
              {{ item.objective }} · {{ when(item.updated_at) }}
            </option>
          </select>
        </label>
        <button class="text-link" :disabled="disabled" @click="newCase">新建恢复事项</button>
      </div>
      <form @submit.prevent="run" novalidate>
        <label
          >这次需要处理的问题<textarea
            v-model="objective"
            :disabled="disabled || terminal"
            maxlength="2000"
            @input="changed"
          />
        </label>
        <div class="recovery-inputs">
          <label
            >本次应急预算（元）<input
              v-model="budget"
              :disabled="disabled"
              inputmode="decimal"
              @input="changed"
          /></label>
          <label
            >数量上限（件，可留空）<input
              v-model="quantityCap"
              :disabled="disabled"
              inputmode="numeric"
              @input="changed"
          /></label>
        </div>
        <fieldset
          v-if="availableSuppliers.length > 1"
          :disabled="disabled || terminal"
          class="recovery-suppliers"
        >
          <legend>参与比较的供应商（最多三家；留空则比较全部）</legend>
          <label v-for="supplier in availableSuppliers" :key="supplier"
            ><input v-model="suppliers" type="checkbox" :value="supplier" @change="changed" />{{
              supplier
            }}</label
          >
        </fieldset>
        <details>
          <summary>补充七日需求情景（没有可用日预测时填写）</summary>
          <p class="source-note">
            这些数值作为你提供的情景假设保存，不作为模型预测或真实销量。留空时使用当前有效日预测；已有事项留空则保留原需求设定。
          </p>
          <label
            >七日需求（件，逗号分隔）<input
              v-model="demand"
              :disabled="disabled"
              placeholder="逐日填写七个数值"
              @input="changed"
          /></label>
          <label
            >首日结算时间（UTC）<input
              v-model="settlement"
              :disabled="disabled"
              type="datetime-local"
              @input="changed"
          /></label>
        </details>
        <div class="recovery-actions">
          <button
            class="primary"
            :disabled="
              disabled || ['CLOSED', 'CANCELLED', 'RESOLVED'].includes(detail?.status || '')
            "
            type="submit"
          >
            {{ detail ? '按新要求重新分析' : '开始分析' }}
          </button>
          <button
            v-if="detail"
            class="secondary"
            type="button"
            :disabled="disabled || editing || terminal"
            @click="recheck"
          >
            重新核对最新依据
          </button>
        </div>
      </form>
      <p v-if="validation || error" role="alert" class="notice amber">{{ validation || error }}</p>
      <p v-if="syncError" role="status" class="notice amber">{{ syncError }}</p>
      <div v-if="pending" class="notice amber">
        <p>原提交的结果尚未确认，其他操作暂不可用。</p>
        <button class="secondary" :disabled="busy || revoked" @click="retry">
          核实并重试原提交
        </button>
      </div>
      <p v-if="notice" role="status" class="notice">{{ notice }}</p>
      <div v-if="detail" class="recovery-result">
        <div class="recovery-heading">
          <h3>{{ labels[detail.status] || detail.status }}</h3>
          <span>第 {{ detail.current_revision }} 版 · {{ when(detail.updated_at) }}</span>
        </div>
        <p v-if="prepared">已生成待确认计划，采购仍需你确认。</p>
        <p v-else-if="detail.plan_id">
          已关联第 {{ detail.plan_revision }} 版恢复计划（{{
            detail.plan_status
          }}）；采购受理与到货状态请查看下方采购记录。
        </p>
        <p v-if="detail.execution_status">实际执行状态：{{ detail.execution_status }}</p>
        <ul v-if="detail.missing_inputs.length" class="notice amber">
          <li v-for="input in detail.missing_inputs" :key="input">{{ input }}</li>
        </ul>
        <p v-if="detail.proposal && stale" class="notice amber">
          当前候选尚未对应最新可执行条件，请重新分析或核对。
        </p>
        <div v-if="detail.proposal" class="recovery-candidates">
          <article
            v-for="candidate in detail.proposal.candidates"
            :key="candidate.id"
            :data-recovery-candidate="candidate.id"
            class="recovery-candidate"
          >
            <h4>
              {{
                candidate.quantity === 0
                  ? '等待原订单'
                  : `${candidate.supplier_id} · ${candidate.quantity} 件`
              }}
              <span v-if="candidate.id === detail.proposal.recommended_candidate_id" class="tag"
                >推荐</span
              >
            </h4>
            <dl>
              <div>
                <dt>新采购支出</dt>
                <dd>{{ money(candidate.spend_minor) }}</dd>
              </div>
              <div>
                <dt>预计缺货</dt>
                <dd>{{ candidate.lost_qty }} 件</dd>
              </div>
              <div>
                <dt>期末库存</dt>
                <dd>{{ candidate.end_stock }} 件</dd>
              </div>
              <div>
                <dt>采购后现金</dt>
                <dd>{{ money(candidate.cash_after_minor) }}</dd>
              </div>
            </dl>
            <p v-if="candidate.rejection_reasons.length" class="notice amber">
              {{ candidate.rejection_reasons.map((r) => reasons[r] || r).join('；') }}
            </p>
            <details v-if="candidate.daily.length">
              <summary>逐日库存与缺口</summary>
              <div class="recovery-table">
                <table>
                  <thead>
                    <tr>
                      <th>结算时间</th>
                      <th>需求</th>
                      <th>原订单到货</th>
                      <th>应急到货</th>
                      <th>缺货</th>
                      <th>期末库存</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="day in candidate.daily" :key="day.settlement_at">
                      <td>{{ when(day.settlement_at) }}</td>
                      <td>{{ day.demand_qty }}</td>
                      <td>{{ day.existing_arrivals }}</td>
                      <td>{{ day.proposed_arrivals }}</td>
                      <td>{{ day.lost_qty }}</td>
                      <td>{{ day.end_stock }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </details>
            <button
              v-if="candidate.quantity > 0"
              class="secondary"
              :disabled="
                disabled || stale || !candidate.feasible || !candidate.executable || prepared
              "
              @click="adopt(candidate)"
            >
              生成待确认方案
            </button>
            <button
              v-else
              class="secondary"
              :disabled="disabled || stale || !candidate.feasible"
              @click="recovery.control('adopt_waiting')"
            >
              采用等待方案
            </button>
          </article>
        </div>
        <details v-if="detail.evidence.length">
          <summary>依据与情景假设</summary>
          <ul class="recovery-evidence">
            <li v-for="source in detail.evidence" :key="source.id">
              <strong>{{
                {
                  verified_source: '业务来源',
                  user_assumption: '用户情景假设',
                  unresolved: '尚待核实',
                }[source.status]
              }}</strong>
              · {{ source.summary }}<small>{{ source.kind }} · {{ source.version }}</small>
            </li>
          </ul>
        </details>
        <details v-if="experts">
          <summary>
            专家分析 · {{ expertStatuses[experts.status || ''] || experts.status
            }}<template v-if="experts.strategy">
              · {{ expertStrategies[experts.strategy] || experts.strategy }}</template
            >
          </summary>
          <p class="source-note">专家负责解释与核对；金额和数量以以上试算结果为准。</p>
          <p v-for="dispute in expertDisputes" :key="dispute" class="notice amber">
            {{ dispute }}
          </p>
          <p v-if="experts.merged?.clarification" class="notice amber">
            需要补充：{{ experts.merged.clarification.question }}
          </p>
          <article v-for="subtask in experts.subtasks || []" :key="subtask.subtask_id">
            <h4>
              {{ expertRoles[subtask.role || subtask.subtask_id] || subtask.subtask_id
              }}<template v-if="subtask.subtask_id.endsWith(':followup')">（补查）</template> ·
              {{ expertStatuses[subtask.status] || subtask.status }}
            </h4>
            <ul>
              <li v-for="(claim, index) in subtask.claims || []" :key="index">
                {{ claim.statement }}<small>依据：{{ claim.support.join('、') }}</small>
              </li>
            </ul>
            <p v-if="subtask.missing?.length" class="notice amber">
              {{ subtask.missing.join('；') }}
            </p>
          </article>
        </details>
        <div class="recovery-actions" v-if="!terminal">
          <span>自动跟进：{{ detail.followup_enabled ? '已开启' : '未开启' }}</span
          ><button
            class="secondary"
            :disabled="disabled"
            @click="
              recovery.control(detail.followup_enabled ? 'disable_followup' : 'enable_followup')
            "
          >
            {{ detail.followup_enabled ? '停止自动跟进' : '开启自动跟进' }}
          </button>
        </div>
        <p v-if="detail.followup_enabled" class="source-note">
          后台定期核对真实执行和到货状态；依据变化时会要求重新分析，采购仍需你确认。
        </p>
        <div class="recovery-actions">
          <button class="text-link" :disabled="busy" @click="recovery.load(detail.id)">
            刷新处理状态</button
          ><button
            v-if="!['CLOSED', 'CANCELLED', 'RESOLVED'].includes(detail.status)"
            class="text-link"
            :disabled="disabled"
            @click="recovery.control('cancel')"
          >
            结束这项恢复事项
          </button>
        </div>
        <p class="source-note">结束事项不会取消已发送的采购，也不会结束原备货委托。</p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.recovery-suppliers {
  border: 1px solid #d4dbd6;
  border-radius: 10px;
  padding: 12px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.recovery-suppliers label {
  display: flex !important;
  align-items: center;
  gap: 6px;
}
.recovery-suppliers input {
  width: auto !important;
}
.recovery-evidence {
  padding-left: 20px;
}
.recovery-evidence li {
  margin: 12px 0;
}
.recovery-workspace small {
  display: block;
  color: #607468;
  overflow-wrap: anywhere;
  margin-top: 4px;
}
.recovery-workspace {
  margin: 16px 0;
  padding: 20px;
}
.recovery-toggle {
  font-size: 1.1rem;
  font-weight: 650;
}
.recovery-workspace form {
  display: grid;
  gap: 14px;
  margin: 16px 0;
}
.recovery-workspace label {
  display: grid;
  gap: 6px;
  font-size: 0.9rem;
}
.recovery-workspace input,
.recovery-workspace textarea,
.recovery-workspace select {
  width: 100%;
  border: 1px solid #d4dbd6;
  border-radius: 10px;
  padding: 10px;
  background: #fff;
  color: #203b31;
}
.recovery-workspace textarea {
  min-height: 76px;
  resize: vertical;
}
.recovery-inputs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.recovery-actions,
.recovery-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 14px 0;
}
.recovery-heading span,
.source-note {
  font-size: 0.85rem;
  color: #607468;
}
.recovery-candidates {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}
.recovery-candidate {
  border: 1px solid #dce6dd;
  border-radius: 14px;
  padding: 16px;
  background: #ffffffa8;
}
.recovery-candidate h4 {
  margin: 0 0 14px;
}
.recovery-candidate dl > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin: 8px 0;
}
.recovery-candidate dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.recovery-candidate dt {
  color: #607468;
}
.recovery-workspace summary {
  cursor: pointer;
  padding: 8px 0;
}
.recovery-table {
  overflow: auto;
}
.recovery-table table {
  border-collapse: collapse;
  font-size: 0.8rem;
  min-width: 540px;
}
.recovery-table td,
.recovery-table th {
  padding: 8px;
  text-align: left;
  border-bottom: 1px solid #e2e8e3;
}
.recovery-workspace pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 0.8rem;
}
.recovery-workspace button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
@media (max-width: 600px) {
  .recovery-inputs {
    grid-template-columns: 1fr;
  }
  .recovery-workspace {
    padding: 14px;
  }
  .recovery-candidates {
    grid-template-columns: 1fr;
  }
}
</style>
