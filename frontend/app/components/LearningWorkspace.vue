<script setup lang="ts">
import type { LearningAsset } from '~/types/learning'
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
</script>
<template>
  <section class="learning-workspace">
    <button class="text-link" @click="emit('navigate', 'today')">返回今日</button>
    <header>
      <h1>学习与经验</h1>
      <p>从你的经营操作中整理可复用的做法，保留来源、适用条件和质量记录。</p>
    </header>
    <p v-if="unavailable">当前环境尚未开启经验学习。已有经营功能可正常使用。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="pending" role="status">
      <p>上次提交结果尚未确认。请重试原提交以核实结果。</p>
      <button class="secondary" :disabled="busy" @click="learning.retry">核实并重试</button>
    </div>
    <template v-if="data">
      <section class="learning-settings">
        <h2>学习设置</h2>
        <p>只从开启后的操作开始记录，按独立经营事项计数。同一事项的多轮对话不会重复计数。</p>
        <label for="learning-mode">学习方式</label>
        <select
          id="learning-mode"
          :value="data.policy.mode"
          :disabled="!canEdit"
          @change="learning.policy(($event.target as HTMLSelectElement).value as 'off' | 'suggest')"
        >
          <option value="off">关闭学习</option>
          <option value="suggest">整理候选，由我选择启用</option>
          <option v-if="data.policy.mode === 'assist'" value="assist">
            辅助模式（仍需质量准入）
          </option>
        </select>
        <p>
          当前累计 {{ data.progress.eligible_episodes }} 次；首次汇总检查点为
          {{ data.progress.first_checkpoint }} 次。同类操作满足样本条件时也会产生候选。
        </p>
        <p>这些经验来自当前模拟经营环境。关闭学习会停止采集并暂停已启用的经验。</p>
        <button class="text-link" :disabled="busy" @click="learning.load">刷新记录</button>
      </section>
      <p v-if="!data.assets.length">尚无候选经验。开启学习并完成经营操作后，这里会展示提炼结果。</p>
      <article v-for="asset in data.assets" :key="asset.id" class="learning-asset">
        <template v-for="rev in asset.revisions" :key="rev.revision">
          <details :open="rev.revision === asset.revisions[0]?.revision">
            <summary>
              {{ rev.spec.title }} · v{{ rev.revision }} · {{ states[rev.status] || rev.status }}
            </summary>
            <p>{{ rev.spec.summary }}</p>
            <p>
              来源 {{ rev.evidence_ids.length }} 条 ·
              {{ asset.active_revision === rev.revision ? '当前使用版本' : '候选或历史版本' }}
            </p>
            <h4>操作步骤</h4>
            <ol>
              <li v-for="step in rev.spec.procedure" :key="step">{{ step }}</li>
            </ol>
            <h4>异常处理</h4>
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
                检查质量
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
                启用此版本
              </button>
              <button
                v-if="rev.status === 'ACTIVE'"
                class="secondary"
                :disabled="!canEdit"
                @click="learning.transition(asset, rev, 'suspend')"
              >
                暂停使用
              </button>
              <button class="text-link" :disabled="!canEdit" @click="confirmForget = asset.id">
                忘记这项经验
              </button>
            </div>
          </details>
        </template>
        <div v-if="confirmForget === asset.id" role="group" aria-label="确认忘记">
          <p>忘记后，全部版本停用，也不会再使用原来源重新提炼。审计记录会保留。</p>
          <button class="secondary" :disabled="!canEdit" @click="forgetConfirmed(asset)">
            确认忘记</button
          ><button class="text-link" @click="confirmForget = ''">取消</button>
        </div>
      </article>
    </template>
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
