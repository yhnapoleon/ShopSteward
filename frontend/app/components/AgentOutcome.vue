<script setup lang="ts">
import type { Schema } from '~/types/models'
import { money, when, reasonLabel } from '~/utils/presentation'
const props = defineProps<{ outcome: Schema<'BusinessOutcome'> }>()
const shop = useShop()
const selected = (p: Schema<'PlanComparison'>) =>
  p.candidates.find((c) => c.id === p.recommended_candidate_id)
const stale = computed(
  () =>
    props.outcome.after &&
    (props.outcome.after.state_version !== shop.s.dashboard?.state.state_version ||
      props.outcome.after.mission_version !== shop.mission.value?.mission_version),
)
</script>
<template>
  <article class="agent-outcome" :data-outcome="outcome.invocation_id">
    <header>
      <b>{{ outcome.kind === 'evaluation' ? '试算结果 · 未修改方案' : '方案修订回执' }}</b
      ><time>{{ when(outcome.recorded_at) }}</time>
    </header>
    <p v-if="outcome.availability !== 'available'">{{ outcome.reason }}</p>
    <template v-else-if="outcome.before && outcome.after">
      <p class="outcome-lead">
        推荐补货 {{ selected(outcome.before)?.quantity ?? '—' }} →
        {{ selected(outcome.after)?.quantity ?? '—' }} 件
      </p>
      <p>
        {{
          outcome.kind === 'evaluation'
            ? `基于方案 v${outcome.before.plan_version} 的假设比较`
            : `方案 v${outcome.before.plan_version} → v${outcome.after.plan_version}`
        }}
        · 经营状态 v{{ outcome.after.state_version }}
      </p>
      <p>
        本次数量上限：{{
          outcome.after.max_purchase_qty == null
            ? '无额外上限'
            : `${outcome.after.max_purchase_qty} 件`
        }}
        · 现金底线 {{ money(outcome.after.cash_floor_minor) }}
      </p>
      <p v-if="stale" class="notice amber">此为历史结果，当前经营状态或委托版本已变化。</p>
      <details>
        <summary>比较数量、现金与缺货</summary>
        <p class="source-note">表格可横向滚动，查看全部约束。</p>
        <div
          v-for="(p, index) in [outcome.before, outcome.after]"
          :key="index"
          class="outcome-comparison"
        >
          <h4>
            {{ index === 0 ? '原方案' : outcome.kind === 'evaluation' ? '假设结果' : '修订方案' }}
          </h4>
          <div
            class="outcome-table"
            tabindex="0"
            :aria-label="index === 0 ? '原方案候选比较' : '结果候选比较'"
          >
            <table>
              <thead>
                <tr>
                  <th>补货</th>
                  <th>支出</th>
                  <th>采购后现金</th>
                  <th>预计缺货</th>
                  <th>约束判断</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="c in p.candidates"
                  :key="c.id"
                  :class="{ recommended: c.id === p.recommended_candidate_id }"
                >
                  <td>
                    {{ c.quantity }} 件<span v-if="c.id === p.recommended_candidate_id">
                      · 推荐</span
                    >
                  </td>
                  <td>{{ money(c.spend_minor) }}</td>
                  <td>{{ money(c.cash_after_minor) }}</td>
                  <td>{{ c.shortage_qty }} 件</td>
                  <td>
                    {{ c.feasible ? '满足约束' : c.rejection_reasons.map(reasonLabel).join('；') }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </details>
      <p class="source-note">
        {{
          outcome.kind === 'evaluation'
            ? '仅试算，未改现行方案、未采购。'
            : '仅更新待确认方案。停止回答不会撤销此变更；采购需核对当前方案后单独确认。'
        }}
        数值是当时需求和到货假设下的推演。
      </p>
    </template>
  </article>
</template>
