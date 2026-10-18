<script setup lang="ts">
import { t as tr } from '~/i18n'
import { intlLocale } from '~/i18n'
import type { DayRow } from '~/utils/recovery'

// Seven settlement days at a glance: each column is that day's demand, the amber top is what
// cannot be served, and a mark under the date says the new purchase arrives that day. The
// numbers come from the solver's own day-by-day settlement (or the same rule before it runs).
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
</script>
<template>
  <figure v-if="days.length" class="rf-days" :aria-label="label + tr('：') + summary">
    <div class="rf-days-grid" aria-hidden="true">
      <div v-for="d in days" :key="d.at" class="rf-day" :class="{ 'is-short': d.lost > 0 }">
        <span class="rf-day-bar"
          ><span class="rf-day-stack" :style="{ height: (d.demand / peak) * 100 + '%' }"
            ><span
              class="rf-day-lost"
              :style="{ height: (d.demand ? d.lost / d.demand : 0) * 100 + '%' }" /></span
        ></span>
        <span class="rf-day-date">{{ day(d.at) }}</span>
        <span class="rf-day-arrive" :class="{ on: d.arriving > 0 }"
          ><AppIcon v-if="d.arriving > 0" name="truck"
        /></span>
      </div>
    </div>
    <figcaption>
      <span class="rf-key"><i class="rf-key-swatch is-served" />{{ tr('够卖') }}</span
      ><span class="rf-key"><i class="rf-key-swatch is-lost" />{{ tr('缺货') }}</span
      ><span v-if="days.some((d) => d.arriving)" class="rf-key"
        ><AppIcon name="truck" />{{ tr(arrival) }}</span
      >
    </figcaption>
  </figure>
</template>
