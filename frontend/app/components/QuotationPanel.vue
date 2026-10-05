<script setup lang="ts">
import { t as tr } from '~/i18n'
const work = useWorkItems(),
  shop = useShop()
const emit = defineEmits<{ submitted: [id: string] }>()
async function start() {
  const d = work.s.pending
    ? await work.submit(work.s.pending)
    : await work.submit({
        path: '/api/v1/work-items',
        body: { store_id: shop.s.storeId, content: tr('帮我整理供应商报价') },
        key: crypto.randomUUID(),
      })
  if (d) emit('submitted', d.item.id)
}
</script>
<template>
  <p>
    {{
      tr(
        '在同一事项里上传报价 CSV、补充缺失字段和纠正整理要求。原件与每次结果保存在服务器，可以继续追问或换一份资料。',
      )
    }}
  </p>
  <p class="source-note">
    {{ tr('支持中文或英文列名，仅 CNY；缺失字段会保留为待补充，不自动换算币种或采购。') }}
  </p>
  <p v-if="work.s.error" class="notice amber" role="alert">{{ tr(work.s.error) }}</p>
  <button
    class="primary"
    :disabled="work.s.busy || !shop.s.storeId || !shop.s.session?.workIntake"
    @click="start"
  >
    {{ tr(work.s.pending ? '恢复原提交' : '开始报价事项') }}
  </button>
</template>
