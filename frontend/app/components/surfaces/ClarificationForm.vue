<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import type { ClarificationField } from '~/surfaces/types'

// Quick fields for what the item's handler asked. The answer becomes one plain sentence, sent
// like a typed reply and shown before sending; like the clarification card's answer it stays in
// Chinese with the rest of the stored request.
const props = defineProps<{ fields: ClarificationField[] }>()
const emit = defineEmits<{ submit: [text: string] }>()
const id = useId()
const values = reactive<Record<string, string>>({})
const upper = reactive<Record<string, string>>({})
watch(
  () => props.fields.map((f) => f.key + ':' + f.kind).join(),
  () => {
    for (const key of Object.keys(values)) delete values[key]
    for (const key of Object.keys(upper)) delete upper[key]
  },
)
const numeric = (value: string) => value !== '' && Number.isFinite(Number(value))
const answer = computed(() => {
  const parts: string[] = []
  for (const field of props.fields) {
    const value = (values[field.key] || '').trim(),
      most = (upper[field.key] || '').trim()
    if (field.kind === 'range') {
      const low = numeric(value) ? value : '',
        high = numeric(most) ? most : ''
      if (low && high) parts.push(`${field.label} ${low}–${high}`)
      else if (low) parts.push(`${field.label}至少 ${low}`)
      else if (high) parts.push(`${field.label}最多 ${high}`)
    } else if (field.kind === 'number' ? numeric(value) : value)
      parts.push(`${field.label} ${value}`)
  }
  return parts.length ? `补充：${parts.join('；')}。` : ''
})
function submit() {
  if (answer.value) emit('submit', answer.value)
}
</script>
<template>
  <form class="surface-clarify space-clarify-form" @submit.prevent="submit">
    <div
      v-for="field in fields"
      :key="field.key"
      class="space-field"
      :class="{ 'space-field-pair': field.kind === 'range' }"
    >
      <label :for="id + '-' + field.key">{{ field.label }}</label>
      <span v-if="field.kind === 'range'"
        ><input
          :id="id + '-' + field.key"
          v-model="values[field.key]"
          class="text-field"
          type="number"
          inputmode="decimal"
          :placeholder="tr('至少')" /><span aria-hidden="true">–</span
        ><input
          v-model="upper[field.key]"
          class="text-field"
          type="number"
          inputmode="decimal"
          :placeholder="tr('最多')"
          :aria-label="joinText([field.label, tr('最多')], ' ')"
      /></span>
      <input
        v-else
        :id="id + '-' + field.key"
        v-model="values[field.key]"
        class="text-field"
        :type="field.kind === 'number' ? 'number' : field.kind === 'date' ? 'date' : 'text'"
        :inputmode="field.kind === 'number' ? 'decimal' : undefined"
        maxlength="200"
      />
    </div>
    <p v-if="answer" class="source-note space-answer">{{ tr('将发送：{0}', [answer]) }}</p>
    <div class="space-clarify-actions">
      <button class="primary" :disabled="!answer">{{ tr('提交补充') }}</button>
    </div>
  </form>
</template>
