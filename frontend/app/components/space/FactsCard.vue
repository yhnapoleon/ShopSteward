<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { money, number, when } from '~/utils/presentation'

// Current cash, stock, in-transit and receivables as the business API reports them.
const emit = defineEmits<{ open: [name: string]; navigate: [view: string] }>()
const { s, stock } = useShop()
const space = useSpace()
const verified = computed(() => s.connected && s.dashboard?.freshness.status === 'FRESH')
</script>
<template>
  <section
    id="space-facts"
    class="task-facts glass space-target space-facts"
    :class="{ 'target-active': space.isTarget('facts') }"
    :aria-label="tr('任务经营事实')"
  >
    <div class="task-section-heading">
      <h2>{{ tr('经营事实') }}</h2>
      <button class="text-link" @click="emit('navigate', 'overview')">
        {{ tr('经营概览') }}<AppIcon name="arrow-up-right" />
      </button>
      <button class="text-link" @click="emit('open', 'facts')">
        {{ tr(verified ? '查看数据来源' : '数据待核实') }}<AppIcon name="database" />
      </button>
    </div>
    <dl>
      <div>
        <dt>{{ tr(verified ? '可用现金' : '上次已核实现金') }}</dt>
        <dd data-testid="cash">{{ tr(money(s.dashboard?.state.available_cash_minor)) }}</dd>
      </div>
      <div>
        <dt>{{ tr('在库') }}</dt>
        <dd>
          <span data-testid="stock">{{ tr(number(stock?.on_hand)) }}</span
          ><small>{{ ' ' + tr('件') }}</small>
        </dd>
      </div>
      <div>
        <dt>{{ tr('采购在途') }}</dt>
        <dd>
          <span data-testid="inbound">{{ tr(number(stock?.in_transit)) }}</span
          ><small>{{ ' ' + tr('件') }}</small>
        </dd>
      </div>
      <div>
        <dt>{{ tr('待结算') }}</dt>
        <dd data-testid="receivables">{{ tr(money(s.dashboard?.state.receivables_minor)) }}</dd>
      </div>
    </dl>
    <p class="source-note">
      {{
        joinText(
          [
            tr('数据同步 {0}', [when(s.dashboard?.freshness.last_sync_at)]),
            tr('· 待结算资金尚未到账'),
          ],
          ' ',
        )
      }}
    </p>
  </section>
</template>
