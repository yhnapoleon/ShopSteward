<script setup lang="ts">
import type { Schema } from '~/types/models'
import { money, when } from '~/utils/presentation'
const props = defineProps<{
  initial?: Schema<'QuantitySimulationRequest'> | null
  itemId?: string
  itemVersion?: number
}>()
const emit = defineEmits<{ created: [id: string] }>()
const shop = useShop(),
  work = useWorkItems(),
  prefix = useId()
const baseline = ref(shop.s.dashboard?.state)
const sku = ref(props.initial?.sku_id || shop.s.catalog?.products[0]?.sku_id || '')
const supplier = ref(props.initial?.supplier_id || '')
const floor = ref(((props.initial?.cash_floor_minor ?? 30000) / 100).toFixed(2))
const quantities = ref((props.initial?.candidate_quantities || [0, 20, 40, 80]).join(', '))
const customDemand = ref(props.initial?.remaining_demand != null)
const demand = ref(String(props.initial?.remaining_demand ?? ''))
const days = ref(String(props.initial?.horizon_days ?? 7))
const error = ref('')
const offers = computed(() => shop.s.catalog?.offers.filter((o) => o.sku_id === sku.value) || [])
const stock = computed(() => baseline.value?.stocks.find((s) => s.sku_id === sku.value))
const changed = computed(
  () => baseline.value?.state_version !== shop.s.dashboard?.state.state_version,
)
const pendingSimulation = computed(
  () => work.s.pending?.path === `/api/v1/stores/${shop.s.storeId}/simulations`,
)
watch(
  offers,
  (value) => {
    if (!value.some((o) => o.supplier_id === supplier.value))
      supplier.value = value[0]?.supplier_id || ''
  },
  { immediate: true },
)
async function refresh() {
  error.value = ''
  try {
    await shop.refresh(true)
    baseline.value = shop.s.dashboard?.state
  } catch (e) {
    error.value = (e as Error).message
  }
}
async function simulate() {
  error.value = ''
  if (pendingSimulation.value && work.s.pending) {
    const d = await work.submit(work.s.pending)
    if (d) emit('created', d.item.id)
    return
  }
  if (!baseline.value || !sku.value || !supplier.value || changed.value) {
    error.value = '请先刷新并核对当前商品和经营数据。'
    return
  }
  const cash = floor.value.trim()
  const parts = cash.match(/^(\d{1,10})(?:\.(\d{1,2}))?$/)
  const list = quantities.value.split(/[,，、\s]+/).filter(Boolean)
  if (!parts) {
    error.value = '现金底线请填写人民币元，最多两位小数。'
    return
  }
  const cashMinor = Number(parts[1]) * 100 + Number((parts[2] || '').padEnd(2, '0'))
  if (
    !list.length ||
    list.some((q) => !/^\d+$/.test(q) || Number(q) > 1000000) ||
    !list.includes('0') ||
    new Set(list.map(Number)).size !== list.length ||
    list.length < 2 ||
    list.length > 20
  ) {
    error.value = '填写2至20个不同的整数件数，包含0件（不买），每项最多100万件。'
    return
  }
  if (
    customDemand.value &&
    (!/^\d+$/.test(demand.value) ||
      Number(demand.value) > 1000000 ||
      !/^\d+$/.test(days.value) ||
      Number(days.value) < 1 ||
      Number(days.value) > 90)
  ) {
    error.value = '需求为0至100万件的整数，期间为1至90天。'
    return
  }
  const body: Schema<'QuantitySimulationRequest'> = {
    expected_state_version: baseline.value.state_version,
    sku_id: sku.value,
    supplier_id: supplier.value,
    cash_floor_minor: cashMinor,
    candidate_quantities: list.map(Number),
    remaining_demand: customDemand.value ? Number(demand.value) : null,
    horizon_days: customDemand.value ? Number(days.value) : null,
    work_item_id: props.itemId || null,
    expected_work_version: props.itemId ? props.itemVersion : null,
  }
  const result = await work.submit({
    path: `/api/v1/stores/${shop.s.storeId}/simulations`,
    body,
    key: crypto.randomUUID(),
  })
  if (result) emit('created', result.item.id)
}
</script>
<template>
  <form class="quantity-simulation" @submit.prevent="simulate">
    <p>先比较补货的代价。结果会保存，建立委托和采购分别确认。</p>
    <div class="simulation-baseline">
      <div>
        <small>当前可用现金</small><strong>{{ money(baseline?.available_cash_minor) }}</strong>
      </div>
      <div>
        <small>所选商品现货</small><strong>{{ stock?.on_hand ?? '—' }} 件</strong>
      </div>
      <div>
        <small>已在途</small><strong>{{ stock?.in_transit ?? '—' }} 件</strong>
      </div>
    </div>
    <p class="source-note">
      经营时点：{{ when(baseline?.simulation_time) }}；到货影响按本期总量比较。
    </p>
    <fieldset :disabled="work.s.busy || !!work.s.pending">
      <div class="simulation-fields">
        <label :for="prefix + '-sku'"
          >商品<select :id="prefix + '-sku'" v-model="sku" required>
            <option v-for="p in shop.s.catalog?.products" :key="p.sku_id" :value="p.sku_id">
              {{ p.name }}
            </option>
          </select></label
        >
        <label :for="prefix + '-supplier'"
          >供应商报价<select :id="prefix + '-supplier'" v-model="supplier" required>
            <option v-for="o in offers" :key="o.supplier_id" :value="o.supplier_id">
              {{ o.supplier_id }} · {{ money(o.unit_price_minor) }}/件
            </option>
          </select></label
        >
        <label :for="prefix + '-floor'"
          >现金至少保留（元）<input
            :id="prefix + '-floor'"
            v-model="floor"
            inputmode="decimal"
            maxlength="13"
            required
        /></label>
        <label :for="prefix + '-quantities'"
          >比较数量（件，以逗号分隔）<input
            :id="prefix + '-quantities'"
            v-model="quantities"
            maxlength="180"
            required
        /></label>
      </div>
      <label class="simulation-toggle"
        ><input v-model="customDemand" type="checkbox" />用我自己的需求假设</label
      >
      <div v-if="customDemand" class="simulation-fields">
        <label :for="prefix + '-demand'"
          >假设剩余需求（件）<input
            :id="prefix + '-demand'"
            v-model="demand"
            inputmode="numeric"
            maxlength="7"
            required
        /></label>
        <label :for="prefix + '-days'"
          >从当前经营时点起（天）<input
            :id="prefix + '-days'"
            v-model="days"
            inputmode="numeric"
            maxlength="2"
            required
        /></label>
        <p class="source-note">自定义需求仅用于本次试算；建立委托前需要正式需求依据。</p>
      </div>
      <p v-else class="source-note">
        采用当前需求依据：{{ stock?.remaining_demand ?? '未取得' }} 件，使用其原适用期间。
      </p>
    </fieldset>
    <p v-if="changed" class="notice amber">
      经营数据有新变化。<button type="button" class="text-link" @click="refresh">
        刷新试算基线
      </button>
    </p>
    <p v-if="error || work.s.error" class="notice amber" role="alert">
      {{ error || work.s.error }}
    </p>
    <p class="source-note">
      当前支持单商品数量与现金底线比较。“晚两天采购”、多商品共用预算和逐日现金曲线尚不可计算。
    </p>
    <div class="work-card-bottom">
      <button
        type="button"
        class="text-link"
        :disabled="work.s.busy || !!work.s.pending"
        @click="refresh"
      >
        刷新经营数据
      </button>
      <button
        class="primary"
        :disabled="work.s.busy || (!pendingSimulation && (changed || !!work.s.pending))"
      >
        {{
          work.s.busy
            ? '正在计算并保存…'
            : pendingSimulation
              ? '查询并重试原试算'
              : '比较并保存结果'
        }}
      </button>
    </div>
  </form>
</template>
<style scoped>
.quantity-simulation {
  display: grid;
  gap: 18px;
}
.quantity-simulation p {
  margin: 0;
}
.quantity-simulation fieldset {
  border: 0;
  padding: 0;
  min-width: 0;
  display: grid;
  gap: 16px;
}
.simulation-baseline {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 18px;
  background: var(--surface, #f6f6f2);
  border-radius: 16px;
}
.simulation-baseline small,
.simulation-baseline strong {
  display: block;
}
.simulation-baseline strong {
  font-size: 21px;
  margin-top: 6px;
}
.simulation-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.simulation-fields label {
  display: grid;
  gap: 8px;
}
.simulation-fields input,
.simulation-fields select {
  width: 100%;
  min-width: 0;
  min-height: 44px;
  border: 1px solid rgba(100, 120, 140, 0.26);
  border-radius: 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.78);
  color: inherit;
  font: inherit;
  line-height: 1.45;
}
.simulation-fields input:focus-visible,
.simulation-fields select:focus-visible {
  outline: 2px solid #3d7cce;
  outline-offset: 2px;
}
.simulation-toggle {
  display: flex;
  align-items: center;
  gap: 9px;
}
.simulation-toggle input {
  width: auto;
}
@media (max-width: 600px) {
  .simulation-fields {
    grid-template-columns: 1fr;
  }
  .simulation-baseline {
    padding: 12px;
    gap: 8px;
  }
  .simulation-baseline strong {
    font-size: 17px;
  }
}
</style>
