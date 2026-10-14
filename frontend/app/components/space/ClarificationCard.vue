<script setup lang="ts">
import { t as tr } from '~/i18n'

// The assistant asked the owner something. Common questions (budget, dates, quantity, supplier)
// get quick fields; the answer is sent as one plain sentence through the item's conversation,
// exactly as if it had been typed there. Anything else is answered in the conversation itself.
const props = defineProps<{ question: string }>()
const emit = defineEmits<{ changed: []; converse: [] }>()
const work = useWorkItems()
const { s } = work
type Kind = 'money' | 'date' | 'quantity' | 'supplier'
const kinds = computed(() => {
  const text = props.question
  const found: Kind[] = []
  if (/预算|金额|现金|多少钱|资金/.test(text)) found.push('money')
  if (/日期|到货|哪天|哪几天|几号|什么时候|何时|时间/.test(text)) found.push('date')
  if (/数量|多少件|几件|件数/.test(text)) found.push('quantity')
  if (/供应商/.test(text)) found.push('supplier')
  return found
})
const id = useId()
const fields = reactive({ money: '', from: '', to: '', least: '', most: '', supplier: '' })
watch(
  () => props.question,
  () => Object.assign(fields, { money: '', from: '', to: '', least: '', most: '', supplier: '' }),
)
const positive = (value: string) => value.trim() !== '' && Number(value) >= 0
// The message the processor receives; it stays in Chinese like the rest of the stored request.
const answer = computed(() => {
  const parts: string[] = []
  if (kinds.value.includes('money') && positive(fields.money)) parts.push(`预算 ${fields.money} 元`)
  if (kinds.value.includes('date') && fields.from)
    parts.push(
      fields.to && fields.to !== fields.from
        ? `日期 ${fields.from} 至 ${fields.to}`
        : `日期 ${fields.from}`,
    )
  if (kinds.value.includes('quantity')) {
    const least = positive(fields.least) ? fields.least : '',
      most = positive(fields.most) ? fields.most : ''
    if (least && most) parts.push(`数量 ${least}–${most} 件`)
    else if (least) parts.push(`数量至少 ${least} 件`)
    else if (most) parts.push(`数量最多 ${most} 件`)
  }
  if (kinds.value.includes('supplier') && fields.supplier.trim())
    parts.push(`供应商 ${fields.supplier.trim()}`)
  return parts.length ? `补充：${parts.join('；')}。` : ''
})
const error = ref('')
async function submit() {
  if (!answer.value || s.busy || s.pending) return
  error.value = ''
  // The conversation box may hold an unsent draft; keep it instead of sending or losing it.
  const draft = s.input
  s.input = answer.value
  const sent = await work.send()
  if (sent) {
    s.input = draft
    emit('changed')
    return
  }
  if (!s.pending) s.input = draft
  if (s.error || s.pending) error.value = '补充未能确认发送，原因见对话框，可以在那里重试。'
}
</script>
<template>
  <section class="glass work-status-panel space-clarify">
    <h2>{{ tr('还需要你补充') }}</h2>
    <p class="space-question">{{ question }}</p>
    <form v-if="kinds.length" class="space-clarify-form" @submit.prevent="submit">
      <div v-if="kinds.includes('money')" class="space-field">
        <label :for="id + '-money'">{{ tr('预算（元）') }}</label>
        <input
          :id="id + '-money'"
          v-model="fields.money"
          class="text-field"
          type="number"
          min="0"
          step="0.01"
          inputmode="decimal"
        />
      </div>
      <div v-if="kinds.includes('date')" class="space-field space-field-pair">
        <label :for="id + '-from'">{{ tr('日期') }}</label>
        <span
          ><input :id="id + '-from'" v-model="fields.from" class="text-field" type="date" /><span
            aria-hidden="true"
            >–</span
          ><input
            v-model="fields.to"
            class="text-field"
            type="date"
            :min="fields.from || undefined"
            :aria-label="tr('结束日期（可不填）')"
        /></span>
      </div>
      <div v-if="kinds.includes('quantity')" class="space-field space-field-pair">
        <label :for="id + '-least'">{{ tr('数量（件）') }}</label>
        <span
          ><input
            :id="id + '-least'"
            v-model="fields.least"
            class="text-field"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            :placeholder="tr('至少')" /><span aria-hidden="true">–</span
          ><input
            v-model="fields.most"
            class="text-field"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            :placeholder="tr('最多')"
            :aria-label="tr('最多（件）')"
        /></span>
      </div>
      <div v-if="kinds.includes('supplier')" class="space-field">
        <label :for="id + '-supplier'">{{ tr('供应商') }}</label>
        <input
          :id="id + '-supplier'"
          v-model="fields.supplier"
          class="text-field"
          type="text"
          maxlength="80"
        />
      </div>
      <p v-if="answer" class="source-note space-answer">
        {{ tr('将发送：{0}', [answer]) }}
      </p>
      <div class="space-clarify-actions">
        <button class="primary" :disabled="!answer || s.busy || !!s.pending">
          {{ tr('提交补充') }}</button
        ><button type="button" class="text-link" @click="emit('converse')">
          <span class="space-wide">{{ tr('也可以到右侧对话补充') }}</span
          ><span class="space-narrow">{{ tr('也可以在对话中补充') }}</span>
        </button>
      </div>
    </form>
    <button v-else type="button" class="text-link space-converse" @click="emit('converse')">
      <span class="space-wide">{{ tr('到右侧对话补充') }}</span
      ><span class="space-narrow">{{ tr('到对话中补充') }}</span
      ><AppIcon name="arrow-right" />
    </button>
    <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
  </section>
</template>
