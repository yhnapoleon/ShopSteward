<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { Schema } from '~/types/models'
import type { Block, Surface } from '~/surfaces/types'
import { fromOutcome } from '~/surfaces/derive'
import SurfaceRenderer from '~/components/surfaces/SurfaceRenderer.vue'
import { money, when } from '~/utils/presentation'
const props = defineProps<{ outcome: Schema<'BusinessOutcome'> }>()
const shop = useShop()
const stale = computed(
  () =>
    props.outcome.after &&
    (props.outcome.after.state_version !== shop.s.dashboard?.state.state_version ||
      props.outcome.after.mission_version !== shop.mission.value?.mission_version),
)
// The outcome as surface blocks (redesign §9): the figures before → after stay in view, both
// plans' candidates sit in the fold. An outcome never changes, so its id keys the entrance.
const surface = computed(() => fromOutcome(props.outcome, { before: true }))
function part(component: Block['component']): Surface | null {
  const blocks = surface.value?.blocks.filter((b) => b.component === component) || []
  return blocks.length ? { version: 1, blocks } : null
}
const figures = computed(() => part('MetricRow'))
const tables = computed(() => part('PlanComparison'))
</script>
<template>
  <article class="agent-outcome" :data-outcome="outcome.invocation_id">
    <header>
      <b>{{ tr(outcome.kind === 'evaluation' ? '试算结果 · 未修改方案' : '方案修订回执') }}</b
      ><time>{{ tr(when(outcome.recorded_at)) }}</time>
    </header>
    <p v-if="outcome.availability !== 'available'">{{ tr(outcome.reason) }}</p>
    <template v-else-if="outcome.before && outcome.after">
      <SurfaceRenderer
        v-if="figures"
        :surface="figures"
        :identity="outcome.invocation_id + ':figures'"
      />
      <p>
        {{
          joinText([
            tr(
              outcome.kind === 'evaluation'
                ? `基于方案 v${outcome.before.plan_version} 的假设比较`
                : `方案 v${outcome.before.plan_version} → v${outcome.after.plan_version}`,
            ),
            tr('· 经营状态 v'),
            tr(outcome.after.state_version),
          ])
        }}
      </p>
      <p>
        {{
          joinText([
            tr('本次数量上限：'),
            tr(
              outcome.after.max_purchase_qty == null
                ? '无额外上限'
                : `${outcome.after.max_purchase_qty} 件`,
            ),
            tr('· 现金底线'),
            tr(money(outcome.after.cash_floor_minor)),
          ])
        }}
      </p>
      <p v-if="stale" class="notice amber">
        {{ tr('此为历史结果，当前经营状态或委托版本已变化。') }}
      </p>
      <details>
        <summary>{{ tr('比较数量、现金与缺货') }}</summary>
        <p class="source-note">{{ tr('表格可横向滚动，查看全部约束。') }}</p>
        <SurfaceRenderer
          v-if="tables"
          :surface="tables"
          :identity="outcome.invocation_id + ':tables'"
          :animate="false"
        />
      </details>
      <p class="source-note">
        {{
          joinText([
            tr(
              outcome.kind === 'evaluation'
                ? '仅试算，未改现行方案、未采购。'
                : '仅更新待确认方案。停止回答不会撤销此变更；采购需核对当前方案后单独确认。',
            ),
            tr('数值是当时需求和到货假设下的推演。'),
          ])
        }}
      </p>
    </template>
  </article>
</template>
