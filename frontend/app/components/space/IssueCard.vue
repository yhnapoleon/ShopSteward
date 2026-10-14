<script setup lang="ts">
import { t as tr } from '~/i18n'
import { firstSync } from '~/utils/glossary'

// Something blocks a decision: same meaning, words and recovery as the task workspace card.
// A new store's first sync is the one exception: it is said in blue, as information.
const props = defineProps<{ issue: string }>()
const shop = useShop()
const { s } = shop
const error = ref('')
const syncing = computed(() => props.issue === 'stale' && firstSync(s.dashboard?.freshness))
async function recover() {
  error.value = ''
  try {
    if (props.issue === 'confirmation') await shop.recoverApproval()
    else if (props.issue === 'expired' || props.issue === 'changed') await shop.requestCheck()
    else await shop.refresh(true)
  } catch (e) {
    error.value = (e as Error).message
  }
}
</script>
<template>
  <article
    class="attention-card glass space-issue"
    :class="{ 'is-syncing': syncing }"
    :role="syncing ? 'status' : undefined"
  >
    <span class="tag" :class="syncing ? 'blue' : 'amber'">{{
      tr(syncing ? '正在同步' : '需要处理')
    }}</span>
    <h2>
      {{
        tr(
          syncing
            ? '正在首次同步经营数据'
            : issue === 'confirmation'
              ? '确认结果尚未取得'
              : issue === 'unknown'
                ? '采购结果还没有核实'
                : issue === 'changed'
                  ? '经营情况已变化，方案待更新'
                  : issue === 'expired'
                    ? '原方案已过期'
                    : '暂时无法确认最新经营数据',
        )
      }}
    </h2>
    <p>
      {{
        tr(
          syncing
            ? '几秒后自动更新，期间不能确认采购。'
            : issue === 'confirmation' || issue === 'unknown'
              ? '保留原确认与采购记录，先查询结果，避免重复采购。'
              : '先取得最新结果，再核对适用方案。',
        )
      }}
    </p>
    <button :class="syncing ? 'secondary' : 'primary'" :disabled="Boolean(s.busy)" @click="recover">
      {{
        tr(
          issue === 'confirmation'
            ? '查询原确认结果'
            : issue === 'expired' || issue === 'changed'
              ? '重新检查'
              : '刷新原记录',
        )
      }}
    </button>
    <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
  </article>
</template>
