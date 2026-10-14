<script setup lang="ts">
import { t as tr } from '~/i18n'

// A comparison table in its own horizontal scroll area; the recommended row is marked.
defineProps<{
  title?: string
  label?: string
  columns: string[]
  rows: string[][]
  highlightIndex?: number
}>()
</script>
<template>
  <div class="surface-comparison">
    <h4 v-if="title" class="surface-table-title">{{ title }}</h4>
    <div
      class="work-result-table surface-table"
      tabindex="0"
      :aria-label="label || tr('结果表格，可横向滚动')"
    >
      <table>
        <thead>
          <tr>
            <th v-for="(column, index) in columns" :key="index" scope="col">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, index) in rows"
            :key="index"
            :class="{ 'recommended-row': index === highlightIndex }"
          >
            <td v-for="(value, cell) in row" :key="cell">{{ value }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="source-note surface-table-hint">
      {{ tr('左右滑动表格可查看全部数量、现金与判断。') }}
    </p>
  </div>
</template>
