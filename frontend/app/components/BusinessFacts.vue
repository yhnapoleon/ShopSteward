<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { money, number, when } from '~/utils/presentation'
const { s, stock, mission, product, unresolved } = useShop()
defineEmits<{ details: []; mission: []; overview: [] }>()
// Visual scale only; all amounts and business decisions remain backend-owned.
const cashScale = computed(() => {
  const cash = s.dashboard?.state.available_cash_minor
  if (cash == null) return null
  const floor = mission.value?.policy.cash_floor_minor ?? 30000
  const extent = Math.max(cash, floor * 1.35, 1)
  return {
    fill: `${Math.max(0, cash / extent) * 100}%`,
    floor: `${Math.max(0, floor / extent) * 100}%`,
  }
})
</script>
<template>
  <div class="fact-strip" :aria-label="tr('当前经营事实')">
    <span
      >{{ tr(s.connected ? '当前现金' : '上次现金')
      }}<b>{{ tr(money(s.dashboard?.state.available_cash_minor)) }}</b></span
    ><span
      >{{ tr('在库 / 在途')
      }}<b>{{
        joinText([tr(number(stock?.on_hand)), '/', tr(number(stock?.in_transit)), tr('件')])
      }}</b></span
    ><span
      >{{ tr('待结算') }}<b>{{ tr(money(s.dashboard?.state.receivables_minor)) }}</b></span
    >
    <div class="overview-fact-links">
      <button @click="$emit('details')"><AppIcon name="info" />{{ tr('查看来源') }}</button
      ><button @click="$emit('overview')">
        <AppIcon name="chart-no-axes-combined" />{{ tr('经营概览') }}
      </button>
    </div>
  </div>
  <aside class="rail" :aria-label="tr('经营背景')">
    <section class="rail-card glass">
      <div class="rail-title">
        {{ tr('店铺此刻')
        }}<button class="overview-entry" @click="$emit('overview')">
          {{ tr('经营概览') }}<AppIcon name="arrow-up-right" />
        </button>
      </div>
      <div class="balance-label">
        {{
          tr(
            s.connected && s.dashboard?.freshness.status === 'FRESH'
              ? '当前可用现金'
              : '上次已核实现金',
          )
        }}
      </div>
      <div class="balance" data-testid="cash">
        {{ tr(money(s.dashboard?.state.available_cash_minor)) }}
      </div>
      <div v-if="cashScale" class="cash-track" aria-hidden="true">
        <span class="cash-track-fill" :style="{ width: cashScale.fill }" />
        <span class="cash-track-floor" :style="{ left: cashScale.floor }" />
      </div>
      <p class="cash-reserve">
        {{ joinText([tr('最低保留'), tr(money(mission?.policy.cash_floor_minor ?? 30000))])
        }}<br /><b v-if="unresolved">{{ tr('采购正在核实') }}</b
        ><b v-else-if="s.dashboard">{{
          joinText([
            tr(
              s.dashboard.state.available_cash_minor >= (mission?.policy.cash_floor_minor ?? 30000)
                ? '高于'
                : '低于',
            ),
            tr('设定底线'),
            tr(
              money(
                Math.abs(
                  s.dashboard.state.available_cash_minor -
                    (mission?.policy.cash_floor_minor ?? 30000),
                ),
              ),
            ),
          ])
        }}</b>
      </p>
      <div class="ledger">
        <div class="ledger-item">
          <span>{{ tr('在库') }}</span
          ><b data-testid="stock">{{ tr(number(stock?.on_hand)) }}</b
          ><small>{{ tr('件') }}</small>
        </div>
        <div class="ledger-item">
          <span>{{ tr('采购在途') }}</span
          ><b data-testid="inbound">{{ tr(number(stock?.in_transit)) }}</b
          ><small>{{ tr('件') }}</small>
        </div>
        <div class="ledger-item wide">
          <span>{{ tr('待结算 · 还未到账') }}</span
          ><b data-testid="receivables">{{ tr(money(s.dashboard?.state.receivables_minor)) }}</b>
        </div>
      </div>
      <button class="data-stamp" :aria-label="tr('查看账目来源')" @click="$emit('details')">
        <AppIcon name="database" />{{
          joinText([tr('业务数据 ·'), tr(when(s.dashboard?.freshness.last_sync_at))])
        }}
      </button>
    </section>
    <section class="rail-card glass">
      <span class="micro">{{ tr('本次经营范围') }}</span>
      <h3>{{ product?.name || tr('请先选择店铺') }}</h3>
      <p>{{ tr('一项活动、一家供应商。') }}<br />{{ tr('采购前核对当前事实。') }}</p>
      <button class="text-link" @click="$emit('mission')">
        {{ tr(mission ? '查看委托与检查安排' : '了解备货跟进') }}<AppIcon name="arrow-up-right" />
      </button>
    </section>
    <p class="autonomy">
      <AppIcon name="shield-check" /><span
        >{{ tr('每笔采购由你确认。') }}<br />{{ tr('当前连接的是合成经营环境。') }}</span
      >
    </p>
  </aside>
</template>
