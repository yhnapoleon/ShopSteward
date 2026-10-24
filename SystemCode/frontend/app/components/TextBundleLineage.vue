<script setup lang="ts">
// The prompts the agents run on are versioned text artifacts. Offline evolution proposes a
// new revision from recorded failures; a revision takes effect only when configuration
// names it. This lists every revision, what it changed, and where it runs today.
import { joinText, t as tr } from '~/i18n'
import { api } from '~/utils/api'
import type { Schema } from '~/types/models'
const items = ref<Schema<'TextBundleEntry'>[]>([]),
  error = ref('')
const bundles: Record<string, string> = {
  'case-experts': '方案解释',
  'supplier-review': '供应商资料审查',
}
const uses: Record<string, string> = {
  case_explanation: '恢复方案的解释',
  sourcing_explanation: '寻源方案的解释',
  supplier_review: '寻源时的资料审查',
}
const stages: Record<string, string> = { explain: '解释环节', read: '阅读环节' }
// What evolution added, shown without the unchanged opening it shares with its parent.
const added = (change: Schema<'BundleChange'>) =>
  change.after.startsWith(change.before)
    ? change.after.slice(change.before.length).trim()
    : change.after
onMounted(async () => {
  try {
    items.value = (await api<Schema<'TextBundleList'>>('/api/v1/text-bundles')).items
  } catch (e) {
    error.value = (e as Error).message
  }
})
</script>
<template>
  <section class="bundle-lineage" data-text-bundles>
    <h2>{{ tr('提示词版本与自进化') }}</h2>
    <p class="lineage-note">
      {{
        tr(
          'Agent 使用的提示词是带版本的文本制品。离线演化根据运行中记录的失败原因提出新版本；新版本只有被配置指定后才生效，输出格式、核对规则和求解器不在可演化范围内。',
        )
      }}
    </p>
    <p v-if="error" class="notice amber" role="alert">{{ tr(error) }}</p>
    <article
      v-for="item in items"
      :key="item.bundle_id + ':' + item.revision"
      class="lineage-item"
      :data-enabled="item.enabled_for.length > 0"
    >
      <h3>
        {{ joinText([tr(bundles[item.bundle_id] || item.bundle_id), '·', item.revision])
        }}<span v-if="item.enabled_for.length" class="tag">{{ tr('使用中') }}</span>
      </h3>
      <p class="lineage-note">
        {{
          item.origin === 'gepa'
            ? joinText([
                tr('由 GEPA 演化得到，父版本'),
                item.parent_revision || '-',
                tr('；演化的是'),
                tr(stages[item.stage || ''] || item.stage || '-'),
                tr('，任务模型'),
                item.task_model || '-',
                tr('，反思模型'),
                item.reflection_model || '-',
                tr('，评测上限 {0} 次', [item.metric_calls ?? '-']),
              ])
            : tr('人工编写的初始版本')
        }}
      </p>
      <p v-if="item.enabled_for.length" class="lineage-note">
        {{ joinText([tr('当前用于：'), item.enabled_for.map((use) => tr(uses[use] || use)).join('、')]) }}
      </p>
      <details v-if="item.changes.length">
        <summary>
          {{ joinText([tr('相对父版本改了'), tr(item.changes.length), tr('处')]) }}
        </summary>
        <div v-for="change in item.changes" :key="change.component" class="lineage-change">
          <b>{{ change.component }}</b>
          <p>{{ added(change) }}</p>
        </div>
      </details>
      <small>{{ item.content_hash }}</small>
    </article>
  </section>
</template>
<style scoped>
.bundle-lineage {
  margin-top: 28px;
  display: grid;
  gap: 12px;
}
.bundle-lineage h2,
.bundle-lineage h3 {
  margin: 0;
}
.lineage-note {
  font-size: 0.88rem;
  color: #607468;
  margin: 0;
}
.lineage-item {
  border: 1px solid #dce6dd;
  border-radius: 14px;
  padding: 14px 16px;
  background: #ffffffa8;
  display: grid;
  gap: 6px;
}
.lineage-item[data-enabled='true'] {
  border-color: #8fb8a0;
}
.lineage-item h3 {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 1rem;
}
.lineage-item summary {
  cursor: pointer;
  padding: 4px 0;
}
.lineage-change p {
  margin: 4px 0 10px;
  font-size: 0.86rem;
  overflow-wrap: anywhere;
}
.lineage-item small {
  color: #8a9a90;
  overflow-wrap: anywhere;
  font-size: 0.72rem;
}
</style>
