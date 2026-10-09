<script setup lang="ts">
import type { SkillRevision } from '~/types/learning'
defineProps<{ revision: SkillRevision }>()
const dimensions: Record<string, string> = {
  S1: '依据与忠实性',
  S2: '适用性与泛化',
  S3: '业务与执行正确性',
  S4: '异常与恢复',
  S5: '相对增量价值',
  S6: '效率与可维护性',
}
const hard: Record<string, string> = {
  H1: '结构与工具契约',
  H2: '权限与数据范围',
  H3: '经营规则',
  H4: '来源与独立性',
  H5: '用户意图与遗忘',
  H6: '预算与恢复',
}
const verdict: Record<string, string> = {
  pass: '通过',
  fail: '未通过',
  insufficient_evidence: '证据不足',
  unknown: '尚未验证',
}
</script>
<template>
  <section class="skill-quality" aria-label="Skill 质量评估">
    <p v-if="revision.latest_check">
      最近检查：{{
        verdict[revision.latest_check.decision.status] || '评估中'
      }}。已启用版本继续按原发布报告及当前依赖校验。
    </p>
    <h4>质量检验 · {{ verdict[revision.quality_decision?.status || 'unknown'] }}</h4>
    <p>独立回放 {{ revision.quality?.independent_cases || 0 }} 例。未验证项目不会按通过处理。</p>
    <dl>
      <template v-for="(name, key) in hard" :key="key"
        ><dt>{{ name }}</dt>
        <dd>{{ verdict[revision.quality?.checks[key] || 'unknown'] }}</dd></template
      >
    </dl>
    <dl>
      <template v-for="(name, key) in dimensions" :key="key"
        ><dt>{{ name }}</dt>
        <dd>
          {{
            revision.quality?.scores[key] == null
              ? '证据不足'
              : `${revision.quality.scores[key]} / 4`
          }}<small v-if="revision.quality?.dimension_reviews[key]?.evidence_refs.length"
            >（附评审证据）</small
          >
        </dd></template
      >
    </dl>
    <p v-if="revision.quality">
      评估有效期至
      {{
        new Date(revision.quality.expires_at).toLocaleString('zh-CN')
      }}，启用与调用时会重新检查依据。
    </p>
    <p v-else>候选尚未评估。需先完成契约检查、独立回放及人工复核。</p>
  </section>
</template>
<style scoped>
.skill-quality {
  background: var(--surface-muted, #f5f6f7);
  padding: 16px;
  border-radius: 12px;
  margin-top: 16px;
}
dl {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  font-size: 14px;
}
dd {
  margin: 0;
}
p {
  font-size: 13px;
  color: #596169;
}
</style>
