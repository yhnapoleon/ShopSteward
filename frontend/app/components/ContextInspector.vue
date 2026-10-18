<script setup lang="ts">
import { api, ApiFailure } from '~/utils/api'
import type { Schema } from '~/types/models'

const props = defineProps<{ runId: string }>()
const shop = useShop()
const expanded = ref(false),
  loading = ref(false),
  error = ref('')
const data = ref<Schema<'ContextInspection'> | null>(null)
let epoch = 0
const scope = computed(() =>
  [
    props.runId,
    shop.s.storeId,
    shop.s.missionId,
    shop.s.session?.principal_id,
    ...(shop.s.session?.roles || []),
  ].join(':'),
)
const profile = computed(() => object(data.value?.config?.profile))
function object(value: unknown): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, any>)
    : {}
}
function list(value: unknown): any[] {
  return Array.isArray(value) ? value : []
}
const reason: Record<string, string> = {
  admission: '不属于本轮输入',
  budget: '超过上下文预算',
  permission: '权限不允许',
  stale: '已过期',
  source_unavailable: '来源不可用',
}
const status: Record<string, string> = {
  reserved: '请求已登记',
  succeeded: '已返回',
  complete: '已返回',
  failed: '失败',
  unknown: '结果待核实',
  cancelled: '已停止',
}
async function refresh() {
  if (loading.value) return
  const n = epoch
  loading.value = true
  error.value = ''
  try {
    const value = await api<Schema<'ContextInspection'>>(
      `/api/v1/agent-runs/${encodeURIComponent(props.runId)}/context`,
    )
    if (n === epoch && value.run_id === props.runId) data.value = value
  } catch (e) {
    if (n !== epoch) return
    error.value = (e as Error).message
    if (e instanceof ApiFailure && [401, 403, 404].includes(e.status)) data.value = null
  } finally {
    if (n === epoch) loading.value = false
  }
}
async function toggle() {
  expanded.value = !expanded.value
  if (expanded.value) await refresh()
}
watch(scope, () => {
  epoch++
  data.value = null
  error.value = ''
  expanded.value = false
  loading.value = false
})
onUnmounted(() => {
  epoch++
})
</script>

<template>
  <section class="context-inspector" aria-label="上下文记录">
    <button class="text-link" :aria-expanded="expanded" @click="toggle">查看上下文记录</button>
    <div v-if="expanded" class="context-body">
      <p class="source-note">查看本轮采用的输入来源、模型配置和调用记录。</p>
      <p v-if="error" role="alert" class="notice amber">{{ error }}</p>
      <p v-if="loading" role="status">正在读取…</p>
      <template v-if="data">
        <dl class="context-profile">
          <div>
            <dt>冻结模型</dt>
            <dd>{{ profile.model_id || '未记录' }}</dd>
          </div>
          <div>
            <dt>接口</dt>
            <dd>{{ profile.api_mode || '未记录' }}</dd>
          </div>
          <div>
            <dt>配置版本</dt>
            <dd>{{ profile.profile_id || '未记录' }} / {{ profile.version || '1' }}</dd>
          </div>
        </dl>
        <p v-if="!data.calls.length" class="source-note">本轮尚无模型调用记录。</p>
        <ol class="context-calls">
          <li v-for="(call, index) in data.calls" :key="index">
            <strong
              >第 {{ call.call_index }} 次 · {{ call.role }} ·
              {{ status[String(call.status)] || call.status }}</strong
            >
            <p>
              {{
                call.usage_status === 'exact'
                  ? `用量 ${object(call.usage).total_tokens ?? '总量未返回'} tokens`
                  : '用量未知'
              }}
              · 费用未知<span v-if="call.error_code"> · {{ call.error_code }}</span>
            </p>
            <small v-if="call.returned_model">实际返回模型：{{ call.returned_model }}</small>
          </li>
        </ol>
        <details v-for="(frame, index) in data.frames" :key="index">
          <summary>
            本轮任务约束 · {{ frame.validation_status === 'validated' ? '已验证' : '保留用户原话' }}
          </summary>
          <p>用户来源：{{ list(frame.source_message_ids).join('、') || '无' }}</p>
          <ul>
            <li v-for="(constraint, i) in list(frame.constraints)" :key="i">
              {{ constraint.key }} {{ constraint.operator }} {{ constraint.value }}
              {{ constraint.unit }}
              <blockquote>{{ constraint.exact_quote }}</blockquote>
            </li>
          </ul>
          <p v-if="list(frame.unresolved).length" class="notice amber">
            尚待明确：{{ list(frame.unresolved).join('；') }}
          </p>
        </details>
        <details v-for="(manifest, index) in data.manifests" :key="index">
          <summary>
            第 {{ index + 1 }} 次上下文选取 · {{ list(manifest.selected_source_ids).length }} 项来源
          </summary>
          <p>已采用：{{ list(manifest.selected_source_ids).join('、') || '无' }}</p>
          <ul>
            <li v-for="(item, i) in list(manifest.omitted)" :key="i">
              {{ item.source_id }} · {{ reason[item.reason] || item.reason }}
            </li>
          </ul>
          <p v-if="manifest.token_budget">
            输入估算 {{ object(manifest.token_budget).estimated_input_tokens }} / 上限
            {{ object(manifest.token_budget).max_input_tokens }} tokens（不是实际计费用量）
          </p>
        </details>
      </template>
      <button class="text-link" :disabled="loading" @click="refresh">刷新记录</button>
    </div>
  </section>
</template>

<style scoped>
.context-inspector {
  margin: 12px 0;
  border-top: 1px solid #dce6dd;
  padding-top: 12px;
}
.context-body {
  font-size: 0.85rem;
  overflow-wrap: anywhere;
}
.context-profile div {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  margin: 6px 0;
}
.context-profile dd {
  margin: 0;
}
.context-calls {
  padding-left: 22px;
}
.context-calls li {
  margin: 12px 0;
}
.context-body summary {
  padding: 8px 0;
  cursor: pointer;
}
.context-body blockquote {
  margin: 8px 0;
  padding-left: 12px;
  border-left: 2px solid #b7c7be;
}
.context-body small,
.source-note {
  color: #607468;
}
</style>
