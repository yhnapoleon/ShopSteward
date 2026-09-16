<script setup lang="ts">
import { intlLocale, locale } from '~/i18n'

import { joinText, t as tr } from '~/i18n'
import { localizedSamples, processQuotes, quoteCSV, downloadFile } from '~/utils/quotations'
import type { QuoteResult, QuoteRule } from '~/utils/quotations'
const file = ref<HTMLInputElement>(),
  input = ref<{ name: string; text: string } | null>(null),
  result = ref<QuoteResult | null>(null),
  history = ref<QuoteResult[]>([]),
  rule = ref<QuoteRule | null>(null),
  preference = ref('unit'),
  error = ref(''),
  editing = ref(false)
const key = 'ss.local-quotes.v1'
onMounted(() => {
  try {
    const data = JSON.parse(localStorage.getItem(key) || 'null')
    if (data && Array.isArray(data.history)) {
      history.value = data.history
      rule.value = data.rule
      preference.value = data.preference || 'unit'
      result.value = data.history.at(-1) || null
    }
  } catch {}
})
function persist() {
  try {
    localStorage.setItem(
      key,
      JSON.stringify({
        history: history.value.slice(-10),
        rule: rule.value,
        preference: preference.value,
      }),
    )
  } catch {
    error.value = '浏览器无法保存资料；当前结果仍可下载。'
  }
}
function selectSample(i: number) {
  input.value = localizedSamples()[i]!
  result.value = null
  error.value = ''
}
async function readFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  if (f.size > 200000 || !f.name.toLowerCase().endsWith('.csv')) {
    error.value = '请选择200KB以内的CSV文件。'
    return
  }
  input.value = { name: f.name, text: await f.text() }
  result.value = null
  error.value = ''
}
function process() {
  if (!input.value) return
  try {
    result.value = processQuotes(input.value.name, input.value.text, rule.value)
    history.value.push(result.value)
    persist()
  } catch (e) {
    error.value = (e as Error).message
  }
}
function saveRule() {
  rule.value = {
    version: (rule.value?.version || 0) + 1,
    source: result.value!.name,
    text: '按单件价排序，保留单位、包装、起订量与来源；缺字段不猜测。',
  }
  editing.value = false
  persist()
}
function togglePreference() {
  preference.value = preference.value === 'unit' ? 'source' : 'unit'
  persist()
}
function clearRule() {
  rule.value = null
  persist()
}
const quoteMoney = (n: number | null) =>
  n === null
    ? '暂不能计算'
    : new Intl.NumberFormat(intlLocale(), {
        style: 'currency',
        currency: 'CNY',
        currencyDisplay: locale.value === 'en' ? 'code' : 'symbol',
        maximumFractionDigits: 2,
      }).format(n)
</script>
<template>
  <p>
    {{
      tr(
        '把报价换成可比较的单件价，同时保留包装、起订量与来源。资料只在本浏览器处理，不改变经营账目。',
      )
    }}
  </p>
  <div class="quote-stage">
    <span>{{ tr('1 选择资料') }}</span
    ><span :class="{ active: input && !result }">{{ tr('2 整理与核对') }}</span
    ><span :class="{ active: result }">{{ tr('3 取得结果') }}</span>
  </div>
  <div class="file-picker">
    <label class="field-label" for="quote-file">{{
      tr('选择报价CSV（仅本机读取，最大200KB）')
    }}</label
    ><input
      id="quote-file"
      ref="file"
      type="file"
      accept=".csv,text/csv"
      hidden
      @change="readFile"
    /><button class="secondary" @click="file?.click()">{{ tr('选择本地 CSV 文件') }}</button>
    <div class="demo-actions">
      <button class="secondary" @click="selectSample(0)">{{ tr('使用示例报价甲') }}</button
      ><button class="secondary" @click="selectSample(1)">{{ tr('换一份示例报价乙') }}</button
      ><button class="text-link" @click="selectSample(2)">{{ tr('体验缺字段资料') }}</button
      ><button
        class="text-link"
        @click="
          downloadFile(
            tr('报价格式模板.csv'),
            localizedSamples()[0]!.text,
            'text/csv;charset=utf-8',
          )
        "
      >
        {{ tr('下载格式模板') }}
      </button>
    </div>
    <p class="source-note">
      {{
        tr(
          '支持固定列名：商品、报价金额、币种、计价单位、每包装件数、最低订购量、MOQ单位、来源。仅CNY，不做汇率换算。',
        )
      }}
    </p>
  </div>
  <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
  <section v-if="input && !result" class="loaded-file">
    <h3>{{ input.name }}</h3>
    <p>{{ tr('已读取文件，尚未整理。') }}</p>
    <button class="primary" @click="process">{{ tr('开始整理') }}</button>
  </section>
  <section v-if="result" class="quote-result">
    <h3>{{ result.name }}</h3>
    <span class="tag" :class="result.issues.length ? 'amber' : 'green'">{{
      tr(result.issues.length ? '部分结果需补资料' : '已整理')
    }}</span>
    <p v-if="result.rule" class="notice">
      {{
        joinText([
          tr('本次使用已保存的本地整理要求，来源：'),
          result.rule.source,
          tr('。按这份新资料重新计算。'),
        ])
      }}
    </p>
    <div v-if="result.issues.length" class="notice amber">
      <b>{{ tr('缺失或不能确定的内容') }}</b>
      <ul>
        <li v-for="item in result.issues" :key="item">{{ tr(item) }}</li>
      </ul>
      <p>{{ tr('已知结果保留，缺失字段不猜测、不当成0。') }}</p>
    </div>
    <article v-for="r in result.rows" :key="r.record" class="quotation-item">
      <h3>{{ r.product }}</h3>
      <p v-if="preference === 'source'" class="quote-source">
        {{
          joinText([tr('来源：'), r.source || tr('未提供'), tr('· 第'), tr(r.record), tr('条资料')])
        }}
      </p>
      <div class="quote-grid">
        <div class="quote-box">
          <h4>{{ tr('单件价') }}</h4>
          <b
            >{{ tr(quoteMoney(r.unitPrice))
            }}<small v-if="r.unitPrice !== null">{{ tr('/ 件') }}</small></b
          >
          <p>{{ tr(r.basis) }}</p>
        </div>
        <div class="quote-box">
          <h4>{{ tr('最低订购量') }}</h4>
          <b>{{ tr(r.moq && r.moqUnit ? `${r.moq} ${r.moqUnit}` : '未完整提供') }}</b>
          <p>{{ tr(r.moqPieces === null ? '折算件数暂缺' : `折合 ${r.moqPieces} 件`) }}</p>
        </div>
      </div>
      <p>
        {{
          joinText([
            tr('原报价：'),
            tr(r.price === null ? '未提供' : r.price),
            tr(r.currency || '币种未提供'),
            '/',
            tr(r.unit || '未提供'),
            tr('· 包装：'),
            tr(r.pack === null ? '未提供' : r.pack + ' 件'),
          ])
        }}
      </p>
      <p v-if="preference !== 'source'" class="quote-source">
        {{
          joinText([tr('来源：'), r.source || tr('未提供'), tr('· 第'), tr(r.record), tr('条资料')])
        }}
      </p>
    </article>
    <div class="result-controls">
      <span>{{ tr('结果展示顺序') }}</span
      ><button class="secondary" @click="togglePreference">
        {{ tr(preference === 'unit' ? '单件价在前' : '来源在前') }}
      </button>
    </div>
    <div v-if="editing" class="notice">
      <p>
        {{
          tr(
            '以后按单件价排序；保留单位、包装、起订量与来源；缺字段不猜测。当前结果保持不变，下一份资料采用。',
          )
        }}
      </p>
      <button class="primary" @click="saveRule">{{ tr('以后按这些步骤整理') }}</button>
    </div>
    <div class="modal-actions">
      <button class="secondary" @click="editing = true">{{ tr('记下以后的整理要求') }}</button
      ><button
        class="primary"
        @click="
          downloadFile(
            result!.name.replace(/\.csv$/i, '') + tr('_整理结果.csv'),
            quoteCSV(result!),
            'text/csv;charset=utf-8',
          )
        "
      >
        {{ tr('保存本次结果') }}
      </button>
    </div>
  </section>
  <details v-if="history.length > 1" class="knowledge-note">
    <summary>{{ tr('以前的整理结果') }}</summary>
    <div class="demo-actions">
      <button v-for="(r, i) in history" :key="i" class="secondary" @click="result = r">
        {{ r.name }}
      </button>
    </div>
  </details>
  <details v-if="rule" class="knowledge-note">
    <summary>{{ tr('已保存的本地整理要求') }}</summary>
    <p>{{ joinText([rule.text, tr('· 来源'), rule.source]) }}</p>
    <button class="text-link" @click="clearRule">{{ tr('撤回要求') }}</button>
  </details>
  <p class="source-note">
    {{ tr('本地资料工具已实现；后端尚无报价处理接口，这不是Agent技能学习或L-01端到端验收。') }}
  </p>
</template>
