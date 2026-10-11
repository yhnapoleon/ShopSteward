<script setup lang="ts">
import { t as tr } from '~/i18n'
import { localizedSamples, downloadFile } from '~/utils/quotations'
const work = useWorkItems(),
  input = ref<HTMLInputElement>(),
  error = ref(''),
  reading = ref(false)
const emit = defineEmits<{ changed: [] }>()
const disabled = computed(
  () => reading.value || work.s.busy || !!work.s.pending || work.s.accessRevoked,
)
async function upload(filename: string, content: string) {
  error.value = ''
  const d = await work.quotation('quotation-files', { filename, content })
  if (d) emit('changed')
}
async function readFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  error.value = ''
  if (!file.name.toLowerCase().endsWith('.csv') || file.size > 200000) {
    error.value = '请选择200KB以内的CSV文件。'
    return
  }
  const epoch = work.s.epoch,
    id = work.s.selected
  reading.value = true
  try {
    const content = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(
      await file.arrayBuffer(),
    )
    if (epoch === work.s.epoch && id === work.s.selected) await upload(file.name, content)
  } catch {
    error.value = '文件无法读取，请使用 UTF-8 编码的 CSV。'
  } finally {
    reading.value = false
    if (input.value) input.value.value = ''
  }
}
async function sample(index: number) {
  const value = localizedSamples()[index]!
  await upload(value.name, value.text)
}
</script>
<template>
  <details class="quotation-attachment">
    <summary>{{ tr('添加报价 CSV') }}</summary>
    <p class="source-note">
      {{ tr('原件保存在这件事中，最多 200KB。可以在下方对话补充字段或说明整理要求。') }}
    </p>
    <input
      ref="input"
      type="file"
      hidden
      accept=".csv,text/csv"
      :disabled="disabled"
      :aria-label="tr('上传报价 CSV')"
      @change="readFile"
    />
    <button class="secondary" :disabled="disabled" @click="input?.click()">
      {{ tr('选择本地 CSV 文件') }}
    </button>
    <div class="demo-actions">
      <button class="text-link" :disabled="disabled" @click="sample(0)">
        {{ tr('使用示例报价甲') }}
      </button>
      <button class="text-link" :disabled="disabled" @click="sample(1)">
        {{ tr('换一份示例报价乙') }}
      </button>
      <button class="text-link" :disabled="disabled" @click="sample(2)">
        {{ tr('体验缺字段资料') }}
      </button>
      <button
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
    <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
  </details>
</template>
