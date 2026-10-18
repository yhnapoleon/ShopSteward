<script setup lang="ts">
import { t as tr } from '~/i18n'
import type { LearningAsset, SkillRevision } from '~/types/learning'
const emit = defineEmits<{ navigate: [view: string] }>()
const learning = useLearning(),
  shop = useShop()
const { data, error, busy, unavailable, pending } = learning
const canEdit = computed(() => shop.hasRole('operator') && !busy.value && !pending.value)
const states: Record<string, string> = {
  DRAFT: '待验证',
  VALIDATING: '验证中',
  SHADOW: '影子评估',
  ACTIVE: '已启用',
  SUSPENDED: '已暂停',
  REJECTED: '未通过',
  SUPERSEDED: '已替代',
  ARCHIVED: '已归档',
  REVOKED: '已忘记',
}
const confirmForget = ref('')
async function forgetConfirmed(asset: LearningAsset) {
  await learning.forget(asset)
  confirmForget.value = ''
}
// asset id and revision of the one the user is about to switch on with limited evidence
const confirmLimited = ref('')
async function enableLimited(asset: LearningAsset, rev: SkillRevision) {
  await learning.transition(asset, rev, 'activate', true)
  confirmLimited.value = ''
}
</script>
<template>
  <section class="learning-workspace">
    <button class="text-link" @click="emit('navigate', 'today')">{{ tr('返回今日') }}</button>
    <header>
      <h1>{{ tr('学习与经验') }}</h1>
      <p>{{ tr('从你的经营操作中整理可复用的做法，保留来源、适用条件和质量记录。') }}</p>
    </header>
    <p v-if="unavailable">{{ tr('当前环境尚未开启经验学习。已有经营功能可正常使用。') }}</p>
    <p v-if="error" role="alert">{{ tr(error) }}</p>
    <div v-if="pending" role="status">
      <p>{{ tr('上次提交结果尚未确认。请重试原提交以核实结果。') }}</p>
      <button class="secondary" :disabled="busy" @click="learning.retry">
        {{ tr('核实并重试') }}
      </button>
    </div>
    <template v-if="data">
      <section class="learning-settings">
        <h2>{{ tr('学习设置') }}</h2>
        <p>
          {{ tr('只从开启后的操作开始记录，按独立经营事项计数。同一事项的多轮对话不会重复计数。') }}
        </p>
        <label for="learning-mode">{{ tr('学习方式') }}</label>
        <select
          id="learning-mode"
          :value="data.policy.mode"
          :disabled="!canEdit"
          @change="learning.policy(($event.target as HTMLSelectElement).value as 'off' | 'suggest')"
        >
          <option value="off">{{ tr('关闭学习') }}</option>
          <option value="suggest">{{ tr('整理候选，由我选择启用') }}</option>
          <option v-if="data.policy.mode === 'assist'" value="assist">
            {{ tr('辅助模式（仍需质量准入）') }}
          </option>
        </select>
        <p>
          {{
            tr('当前累计 {0} 次；首次汇总检查点为 {1} 次。同类操作满足样本条件时也会产生候选。', [
              data.progress.eligible_episodes,
              data.progress.first_checkpoint,
            ])
          }}
        </p>
        <p>
          {{ tr('这些经验来自当前模拟经营环境。关闭学习会停止采集并暂停已启用的经验。') }}
        </p>
        <button class="text-link" :disabled="busy" @click="learning.load">
          {{ tr('刷新记录') }}
        </button>
      </section>
      <p v-if="!data.assets.length">
        {{ tr('尚无候选经验。开启学习并完成经营操作后，这里会展示提炼结果。') }}
      </p>
      <article v-for="asset in data.assets" :key="asset.id" class="learning-asset">
        <template v-for="rev in asset.revisions" :key="rev.revision">
          <details :open="rev.revision === asset.revisions[0]?.revision">
            <summary>
              {{ rev.spec.title }} · v{{ rev.revision }} · {{ tr(states[rev.status] || rev.status)
              }}<template v-if="rev.status === 'ACTIVE' && rev.limited_evidence">
                · {{ tr('证据有限') }}</template
              >
            </summary>
            <p>{{ rev.spec.summary }}</p>
            <p>
              {{
                tr('来源 {0} 条 · {1}', [
                  rev.evidence_ids.length,
                  asset.active_revision === rev.revision
                    ? tr('当前使用版本')
                    : tr('候选或历史版本'),
                ])
              }}
            </p>
            <h4>{{ tr('操作步骤') }}</h4>
            <ol>
              <li v-for="step in rev.spec.procedure" :key="step">{{ step }}</li>
            </ol>
            <h4>{{ tr('异常处理') }}</h4>
            <ul>
              <li v-for="step in rev.spec.exceptions" :key="step">{{ step }}</li>
            </ul>
            <SkillQualityCard :revision="rev" />
            <div v-if="rev.status !== 'REVOKED'" class="learning-actions">
              <button
                class="secondary"
                :disabled="!canEdit || data.policy.mode === 'off'"
                @click="learning.evaluate(asset, rev)"
              >
                {{ tr('检查质量') }}
              </button>
              <button
                class="primary"
                :disabled="
                  !canEdit ||
                  data.policy.mode === 'off' ||
                  rev.quality_decision?.status !== 'pass' ||
                  rev.status === 'ACTIVE'
                "
                @click="learning.transition(asset, rev, 'activate')"
              >
                {{ tr('启用此版本') }}
              </button>
              <button
                v-if="rev.limited_evidence && rev.status !== 'ACTIVE'"
                class="secondary"
                :disabled="!canEdit || data.policy.mode === 'off'"
                @click="confirmLimited = asset.id + ':' + rev.revision"
              >
                {{ tr('按有限证据启用') }}
              </button>
              <button
                v-if="rev.status === 'ACTIVE'"
                class="secondary"
                :disabled="!canEdit"
                @click="learning.transition(asset, rev, 'suspend')"
              >
                {{ tr('暂停使用') }}
              </button>
              <button class="text-link" :disabled="!canEdit" @click="confirmForget = asset.id">
                {{ tr('忘记这项经验') }}
              </button>
            </div>
            <div
              v-if="confirmLimited === asset.id + ':' + rev.revision"
              role="group"
              :aria-label="tr('确认按有限证据启用')"
            >
              <p>
                {{
                  tr(
                    '这个版本只通过了结构与工具契约检查，没有做过独立回放和人工复核。启用后 Agent 会把它当作参考做法；金额、权限和采购确认仍由业务规则把关。页面会一直标明“证据有限”，随时可以暂停。',
                  )
                }}
              </p>
              <button class="primary" :disabled="!canEdit" @click="enableLimited(asset, rev)">
                {{ tr('确认启用') }}</button
              ><button class="text-link" @click="confirmLimited = ''">{{ tr('取消') }}</button>
            </div>
          </details>
        </template>
        <div v-if="confirmForget === asset.id" role="group" :aria-label="tr('确认忘记')">
          <p>{{ tr('忘记后，全部版本停用，也不会再使用原来源重新提炼。审计记录会保留。') }}</p>
          <button class="secondary" :disabled="!canEdit" @click="forgetConfirmed(asset)">
            {{ tr('确认忘记') }}</button
          ><button class="text-link" @click="confirmForget = ''">{{ tr('取消') }}</button>
        </div>
      </article>
    </template>
    <TextBundleLineage />
  </section>
</template>
<style scoped>
.learning-workspace {
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 24px 100px;
}
header {
  margin: 24px 0;
}
.learning-settings,
.learning-asset {
  background: var(--surface, white);
  border: 1px solid #e3e7e9;
  border-radius: 18px;
  padding: 24px;
  margin: 20px 0;
}
select {
  padding: 10px;
  margin-left: 16px;
  border-radius: 8px;
}
summary {
  cursor: pointer;
  font-weight: 600;
  padding: 12px 0;
}
.learning-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}
li {
  margin: 8px 0;
}
button:disabled {
  opacity: 0.45;
}
</style>
