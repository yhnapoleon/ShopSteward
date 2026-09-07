<script setup lang="ts">
import { money, number, when } from '~/utils/presentation'
const { s, stock, mission, product, unresolved } = useShop()
defineEmits<{ details: []; mission: [] }>()
</script>
<template>
  <div class="fact-strip" aria-label="当前经营事实">
    <span
      >{{ s.connected ? '当前现金' : '上次现金'
      }}<b>{{ money(s.dashboard?.state.available_cash_minor) }}</b></span
    ><span
      >在库 / 在途<b>{{ number(stock?.on_hand) }} / {{ number(stock?.in_transit) }} 件</b></span
    ><span
      >待结算<b>{{ money(s.dashboard?.state.receivables_minor) }}</b></span
    ><button @click="$emit('details')"><AppIcon name="info" />查看来源</button>
  </div>
  <aside class="rail" aria-label="经营背景">
    <section class="rail-card glass">
      <div class="rail-title">
        店铺此刻<button class="icon-btn" aria-label="查看账目来源" @click="$emit('details')">
          <AppIcon name="arrow-up-right" />
        </button>
      </div>
      <div class="balance-label">
        {{
          s.connected && s.dashboard?.freshness.status === 'FRESH'
            ? '当前可用现金'
            : '上次已核实现金'
        }}
      </div>
      <div class="balance" data-testid="cash">
        {{ money(s.dashboard?.state.available_cash_minor) }}
      </div>
      <p class="cash-reserve">
        最低保留 {{ money(mission?.policy.cash_floor_minor ?? 30000) }}<br /><b v-if="unresolved"
          >采购正在核实</b
        ><b v-else-if="s.dashboard"
          >{{
            s.dashboard.state.available_cash_minor >= (mission?.policy.cash_floor_minor ?? 30000)
              ? '高于'
              : '低于'
          }}设定底线
          {{
            money(
              Math.abs(
                s.dashboard.state.available_cash_minor -
                  (mission?.policy.cash_floor_minor ?? 30000),
              ),
            )
          }}</b
        >
      </p>
      <div class="ledger">
        <div class="ledger-item">
          <span>在库</span><b data-testid="stock">{{ number(stock?.on_hand) }}</b
          ><small>件</small>
        </div>
        <div class="ledger-item">
          <span>采购在途</span><b data-testid="inbound">{{ number(stock?.in_transit) }}</b
          ><small>件</small>
        </div>
        <div class="ledger-item wide">
          <span>待结算 · 还未到账</span
          ><b data-testid="receivables">{{ money(s.dashboard?.state.receivables_minor) }}</b>
        </div>
      </div>
      <div class="data-stamp">
        <AppIcon name="database" />业务数据 · {{ when(s.dashboard?.freshness.last_sync_at) }}
      </div>
    </section>
    <section class="rail-card glass">
      <span class="micro">本次经营范围</span>
      <h3>{{ product?.name || '请先选择店铺' }}</h3>
      <p>一项活动、一家供应商。<br />采购前核对当前事实。</p>
      <button class="text-link" @click="$emit('mission')">
        {{ mission ? '查看委托与检查安排' : '了解备货跟进' }}<AppIcon name="arrow-up-right" />
      </button>
    </section>
    <p class="autonomy">
      <AppIcon name="shield-check" /><span>每笔采购由你确认。<br />当前连接的是合成经营环境。</span>
    </p>
  </aside>
</template>
