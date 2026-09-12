<script setup lang="ts">
import type { Schema } from '~/types/models'
import { downloadFile } from '~/utils/quotations'
const props = defineProps<{ result: Schema<'WorkResult'>; demonstration?: boolean }>()
function download() {
  const r = props.result
  downloadFile(
    '事项结果.txt',
    (props.demonstration ? '模拟接入结果，非真实 Agent 分析\n\n' : '') +
      r.title +
      '\n\n' +
      r.content +
      '\n\n' +
      [r.columns, ...(r.rows || [])].map((row) => row?.join('\t')).join('\n'),
  )
}
</script>
<template>
  <section class="work-result">
    <div class="work-card-top">
      <h3>{{ result.title }}</h3>
      <button class="text-link" @click="download">保存结果</button>
    </div>
    <p v-if="demonstration" class="notice amber">模拟接入结果，仅验证处理流程。</p>
    <p v-if="result.kind === 'forecast'" class="source-note">
      预测分析，包含假设；不是已发生的经营事实。
    </p>
    <MarkdownMessage :content="result.content" />
    <details v-if="result.assumptions?.length || result.references?.length">
      <summary>依据与假设</summary>
      <ul>
        <li v-for="(a, i) in result.assumptions" :key="'a' + i">{{ a }}</li>
        <li v-for="(r, i) in result.references" :key="'r' + i">
          {{ r.label }}<small> · {{ r.type }} / {{ r.id }}</small>
        </li>
      </ul>
    </details>
    <div
      v-if="result.columns?.length"
      class="work-result-table"
      tabindex="0"
      aria-label="结果表格，可横向滚动"
    >
      <table>
        <thead>
          <tr>
            <th v-for="(c, i) in result.columns" :key="i">{{ c }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in result.rows" :key="i">
            <td v-for="(value, j) in row" :key="j">{{ value }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="source-note">以上为本次处理结果；采购及到货以关联业务记录为准。</p>
  </section>
</template>
