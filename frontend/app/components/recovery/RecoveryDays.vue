<script setup lang="ts">
import { t as tr } from '~/i18n'
import { intlLocale } from '~/i18n'
import type { DayRow } from '~/utils/recovery'

// Seven settlement days at a glance: each column is that day's demand and the amber top is what
// cannot be served, its count written above it; a truck above a column marks the day goods
// arrive, and the first short day's date stands out. The numbers come from the solver's own
// day-by-day settlement (or the same rule before it runs). There is no legend: the sentence above
// the chart already says the gap, and the figure's accessible name repeats it.
const props = withDefaults(defineProps<{ days: DayRow[]; label: string; arrival?: string }>(), {
  arrival: '应急到货',
})
const peak = computed(() => Math.max(1, ...props.days.map((d) => d.demand)))
const short = computed(() => props.days.reduce((n, d) => n + d.lost, 0))
const day = (at: string) =>
  new Date(at).toLocaleDateString(intlLocale(), { month: 'numeric', day: 'numeric' })
const summary = computed(() =>
  short.value
    ? tr('7 天共缺 {0} 件，{1} 起出现缺口', [short.value, day(props.days.find((d) => d.lost)!.at)])
    : tr('7 天内每天都够卖'),
)
const firstShort = computed(() => props.days.find((d) => d.lost)?.at)
const arrivals = computed(() => props.days.filter((d) => d.arriving > 0).map((d) => day(d.at)))
const name = computed(() =>
  [
    props.label + tr('：') + summary.value,
    arrivals.value.length ? tr(props.arrival) + tr('：') + arrivals.value.join(tr('、')) : '',
  ]
    .filter(Boolean)
    .join(tr('；')),
)
</script>
<template>
  <figure v-if="days.length" class="rf-days" role="img" :aria-label="name">
    <div class="rf-days-grid" aria-hidden="true">
      <div v-for="d in days" :key="d.at" class="rf-day" :class="{ 'is-short': d.lost > 0 }">
        <span class="rf-day-note"
          ><AppIcon v-if="d.arriving > 0" name="truck" /><template v-else-if="d.lost">{{
            d.lost
          }}</template></span
        >
        <span class="rf-day-bar"
          ><span class="rf-day-stack" :style="{ height: (d.demand / peak) * 100 + '%' }"
            ><span
              class="rf-day-lost"
              :style="{ height: (d.demand ? d.lost / d.demand : 0) * 100 + '%' }" /></span
        ></span>
        <span class="rf-day-date" :class="{ 'is-first': d.at === firstShort }">{{
          day(d.at)
        }}</span>
      </div>
    </div>
  </figure>
</template>
