<script setup lang="ts">
import { t as tr } from '~/i18n'
import { money, when } from '~/utils/presentation'
import { supplierDisplayName } from '~/utils/glossary'
import {
  caseProblem,
  demandFrom,
  objectiveFor,
  projectWithout,
  recoveryTrigger,
  settlements,
  type DemandPlan,
  unbroken,
} from '~/utils/recovery'
import { useFlow } from '~/composables/useRecoveryFlow'

// Step 1, "说明情况": everything is filled in from the shop's own facts, so the owner only
// confirms. The problem sentence is written from what triggered the restock and the projected
// gap; the budget is what the cash floor leaves; demand is the enabled daily forecast or the
// mission's current assumption; the first settlement follows the business clock (shown only
// under "修改": the owner never has to decide it). When the seven days hold no gap, closing is
// the main action and comparing anyway steps back to a link.
const flow = useFlow()
const shop = useShop()
const { s, mission, stock } = shop
const request = computed(() => flow.brief.value)
// The header button carries no reason: read it from the mission, as the today page does.
const trigger = computed(() =>
  request.value?.reason === 'manual' && mission.value
    ? recoveryTrigger({
        missionId: mission.value.id,
        plan: shop.plan.value,
        actions: s.actions,
        inbounds: s.inbounds,
        alerts: s.alerts,
      })
    : null,
)
const reason = computed(() => trigger.value?.reason || request.value?.reason || 'manual')
const supplier = computed(() => request.value?.exclude || trigger.value?.supplier || null)
const clock = computed(() => s.dashboard?.state.simulation_time || null)
const cash = computed(() => s.dashboard?.state.available_cash_minor ?? 0)
const floor = computed(() => mission.value?.policy.cash_floor_minor ?? 0)
const suggested = computed(() => Math.max(0, cash.value - floor.value))

const editing = ref(false)
const objectiveText = ref('')
const budgetText = ref('')
const flat = ref(false)
const perDayText = ref('')
const base = computed(() =>
  demandFrom({
    forecast: flow.forecast.value,
    plan: shop.plan.value,
    remainingDemand: stock.value?.remaining_demand,
  }),
)
const sum = (values: number[]) => values.reduce((n, v) => n + v, 0)
const perDayDefault = computed(() => Math.round(sum(base.value.values) / 7))
const perDay = computed(() =>
  /^\d+$/.test(perDayText.value.trim()) ? Number(perDayText.value.trim()) : perDayDefault.value,
)
const demand = computed<DemandPlan>(() =>
  flat.value ? { values: Array(7).fill(perDay.value), source: 'daily' } : base.value,
)
const dates = computed(() => (clock.value ? settlements(clock.value) : []))
const projection = computed(() =>
  clock.value && stock.value
    ? projectWithout(
        stock.value.on_hand,
        demand.value.values,
        dates.value,
        s.inbounds
          .filter((i) => i.sku_id === mission.value?.sku_id && i.remaining_quantity > 0)
          .map((i) => ({ quantity: i.remaining_quantity, at: i.expected_arrival_at })),
        clock.value,
      )
    : null,
)
const generated = computed(() => objectiveFor(reason.value, projection.value, supplier.value))
const objective = computed(() => objectiveText.value.trim() || generated.value)
const budgetMinor = computed(() => {
  const text = budgetText.value.trim()
  if (!text) return suggested.value
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) return null
  const [whole, decimal = ''] = text.split('.')
  const minor = Number(whole) * 100 + Number(decimal.padEnd(2, '0'))
  return Number.isSafeInteger(minor) && minor <= 1_000_000_000 ? minor : null
})
const readable = computed(() => flow.directory.readable.value)
const sourcingOn = computed(() => !!s.session?.sourcing)
const names = computed(() =>
  readable.value.map((x) => supplierDisplayName(x.supplier_id, x.name)).join(tr('、')),
)
// Demo mode loads the sample documents by itself; the link is only there when that did not work.
const demo = useDemoMode()
const canSample = computed(
  () =>
    demo.enabled.value &&
    flow.operator.value &&
    !readable.value.length &&
    !flow.directory.state.value.loading,
)
/** No gap in the seven days without a purchase: nothing needs restocking. */
const noGap = computed(() => !!projection.value && projection.value.lost === 0)
const startLabel = computed(() =>
  tr(readable.value.length && sourcingOn.value ? '确认，开始找货' : '确认，开始比价'),
)
/** The Case is being set up: the brief stays in place until the suppliers are being read. */
const starting = computed(() => flow.working.value === 'start')
const error = ref('')
const failure = computed(() =>
  flow.recovery.error.value
    ? caseProblem(flow.recovery.errorCode.value, flow.recovery.error.value)
    : flow.problem.value
      ? caseProblem(flow.problem.value.code, flow.problem.value.message)
      : '',
)
async function sample() {
  error.value = ''
  if (!mission.value) return
  try {
    await flow.directory.loadSample(mission.value.sku_id)
  } catch (e) {
    error.value = (e as Error).message
  }
}
async function confirm() {
  error.value = ''
  if (budgetMinor.value == null) {
    error.value = '预算请输入非负金额，最多两位小数。'
    editing.value = true
    return
  }
  if (flat.value && !/^\d+$/.test(perDayText.value.trim() || String(perDay.value))) {
    error.value = '每天件数请输入非负整数。'
    return
  }
  if (!objective.value.trim()) {
    error.value = '请写一句这次要处理的问题。'
    editing.value = true
    return
  }
  if (!clock.value) {
    error.value = '经营时钟还没有同步，稍后再试。'
    return
  }
  await flow.begin({
    objective: objective.value,
    budgetMinor: budgetMinor.value,
    demand: demand.value,
  })
}
function useFlat(on: boolean) {
  flat.value = on
  if (on && !perDayText.value) perDayText.value = String(perDayDefault.value)
}
</script>
<template>
  <div class="rf-stage rf-brief">
    <h3 v-if="!editing" class="rf-title">{{ unbroken(objective) }}</h3>
    <label v-else class="rf-field rf-field-wide"
      >{{ tr('这次要处理的问题')
      }}<textarea
        v-model="objectiveText"
        rows="2"
        maxlength="2000"
        :placeholder="generated"
        data-recovery-objective
      />
    </label>
    <RecoveryDays
      v-if="projection && projection.lost > 0"
      :days="projection.days"
      :label="tr('不补货的七天')"
      :arrival="'原订单到货'"
    />
    <dl class="rf-facts">
      <div class="rf-fact" data-fact="budget">
        <dt>{{ tr('预算') }}</dt>
        <dd>
          <b v-if="!editing">{{ tr(money(budgetMinor ?? suggested)) }}</b
          ><span v-else class="rf-input-money"
            >¥<input
              v-model="budgetText"
              inputmode="decimal"
              :placeholder="(suggested / 100).toFixed(2)"
              :aria-label="tr('预算（元）')"
          /></span>
          <small>{{
            suggested
              ? tr('可用现金 {0} − 底线 {1}', [money(cash), money(floor)])
              : tr('现金已到底线 {0}，这次买不了', [money(floor)])
          }}</small>
        </dd>
      </div>
      <div class="rf-fact" data-fact="demand">
        <dt>{{ tr('7 天需求') }}</dt>
        <dd>
          <b
            >{{ sum(demand.values) }}<span class="rf-unit">{{ ' ' + tr('件') }}</span></b
          >
          <span class="rf-demand"
            ><span class="rf-basis" role="group" :aria-label="tr('需求按什么填')"
              ><button
                type="button"
                class="text-link"
                :aria-pressed="!flat"
                :disabled="starting"
                @click="useFlat(false)"
              >
                {{ tr(base.source === 'forecast' ? '按预测' : '按估算') }}</button
              ><button
                type="button"
                class="text-link"
                :aria-pressed="flat"
                :disabled="starting"
                @click="useFlat(true)"
              >
                {{ flat ? tr('每天') : tr('每天 {0} 件', [perDayDefault]) }}
              </button></span
            ><span v-if="flat" class="rf-perday"
              ><input
                v-model="perDayText"
                inputmode="numeric"
                :aria-label="tr('每天件数')"
                data-recovery-per-day
              />{{ tr('件') }}</span
            ></span
          >
        </dd>
      </div>
      <div v-if="sourcingOn" class="rf-fact" data-fact="documents">
        <dt>{{ tr('资料在档') }}</dt>
        <dd>
          <b
            >{{ readable.length }}<span class="rf-unit">{{ ' ' + tr('家') }}</span></b
          ><small v-if="readable.length">{{ names }}</small
          ><small v-else-if="flow.directory.state.value.loading">{{ tr('正在读取…') }}</small
          ><button v-else-if="canSample" type="button" class="text-link" @click="sample">
            {{ tr('载入示例资料') }}
          </button>
        </dd>
      </div>
    </dl>
    <p v-if="editing" class="rf-settle" data-fact="settlement">
      {{ tr('首日结算') }}<b>{{ dates[0] ? tr(when(dates[0])) : tr('尚未取得') }}</b
      ><small>{{ tr('按经营时钟，之后每天一次') }}</small>
    </p>
    <p v-if="error || failure" class="notice amber" role="alert">{{ tr(error) || failure }}</p>
    <footer class="rf-next">
      <span class="rf-links"
        ><button
          v-if="!noGap"
          type="button"
          class="text-link"
          :disabled="starting"
          @click="flow.close()"
        >
          {{ tr('关闭') }}</button
        ><button
          type="button"
          class="text-link"
          :aria-pressed="editing"
          :disabled="starting"
          @click="editing = !editing"
        >
          {{ tr(editing ? '改好了' : '修改') }}</button
        ><button
          v-if="noGap"
          type="button"
          class="text-link"
          :disabled="Boolean(flow.working.value) || !flow.operator.value"
          data-recovery-start
          @click="confirm"
        >
          {{ tr('仍要比价') }}
        </button></span
      ><button
        v-if="noGap"
        type="button"
        class="primary"
        data-recovery-next
        data-recovery-close
        @click="flow.close()"
      >
        {{ tr('关闭') }}</button
      ><button
        v-else
        type="button"
        class="primary"
        :disabled="Boolean(flow.working.value) || !flow.operator.value"
        data-recovery-next
        @click="confirm"
      >
        <RecoveryButtonLabel :label="startLabel" :busy="tr('正在建立…')" :working="starting" />
      </button>
    </footer>
  </div>
</template>
