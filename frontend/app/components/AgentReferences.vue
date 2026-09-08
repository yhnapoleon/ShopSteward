<script setup lang="ts">
import { sourceIdentity, sourceLabel } from '~/utils/agent'
const props = defineProps<{ references: unknown[] }>()
const items = computed(() =>
  [...new Map(props.references.map((r) => [sourceIdentity(r), r])).values()].filter(
    (r): r is Record<string, unknown> => !!r && typeof r === 'object',
  ),
)
const fields: Record<string, string> = {
  id: '来源编号',
  version_id: '文档版本',
  generation_id: '检索版本',
  chunk_id: '片段编号',
  metadata_revision: '资料信息版本',
  locator: '原文位置',
  plan_version: '方案版本',
  state_version: '状态版本',
  hash: '内容校验',
  content_hash: '内容校验',
  content_sha256: '片段校验',
  original_sha256: '原件校验',
}
const value = (v: unknown) => (typeof v === 'object' ? JSON.stringify(v) : String(v))
</script>
<template>
  <div v-if="items.length" class="agent-references" aria-label="本轮获取的来源">
    <details v-for="r in items" :key="sourceIdentity(r)" class="agent-source">
      <summary>
        <AppIcon name="file-text" />{{ sourceLabel(r)
        }}<span v-if="r.version_id"> · 有版本记录</span><AppIcon name="chevron-down" />
      </summary>
      <div class="agent-source-body">
        <p>本轮获取的来源，供核对使用。</p>
        <dl>
          <template v-for="(label, field) in fields" :key="field"
            ><div v-if="r[field] != null">
              <dt>{{ label }}</dt>
              <dd>{{ value(r[field]) }}</dd>
            </div></template
          >
        </dl>
        <p v-if="r.chunk_id">此处保留历史定位；原文片段尚未载入。</p>
      </div>
    </details>
  </div>
</template>
