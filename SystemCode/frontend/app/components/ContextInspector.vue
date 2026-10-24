<script setup lang="ts">
import { t as tr } from '~/i18n'
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
  <section class="context-inspector" :aria-label="tr('上下文记录')">
    <button class="text-link" :aria-expanded="expanded" @click="toggle">
      {{ tr('查看上下文记录') }}
    </button>
    <div v-if="expanded" class="context-body">
      <p class="source-note">{{ tr('查看本轮采用的输入来源、模型配置和调用记录。') }}</p>
      <p v-if="error" role="alert" class="notice amber">{{ tr(error) }}</p>
      <p v-if="loading" role="status">{{ tr('正在读取…') }}</p>
      <template v-if="data">
        <dl class="context-profile">
          <div>
            <dt>{{ tr('冻结模型') }}</dt>
            <dd>{{ profile.model_id || tr('未记录') }}</dd>
          </div>
          <div>
            <dt>{{ tr('接口') }}</dt>
            <dd>{{ profile.api_mode || tr('未记录') }}</dd>
          </div>
          <div>
            <dt>{{ tr('配置版本') }}</dt>
            <dd>{{ profile.profile_id || tr('未记录') }} / {{ profile.version || '1' }}</dd>
          </div>
        </dl>
        <p v-if="!data.calls.length" class="source-note">{{ tr('本轮尚无模型调用记录。') }}</p>
        <ol class="context-calls">
          <li v-for="(call, index) in data.calls" :key="index">
            <strong>{{
              tr('第 {0} 次 · {1} · {2}', [
                call.call_index as number,
                call.role as string,
                tr(status[String(call.status)] || (call.status as string)),
              ])
            }}</strong>
            <p>
              {{
                call.usage_status === 'exact'
                  ? tr('用量 {0} tokens', [object(call.usage).total_tokens ?? tr('总量未返回')])
                  : tr('用量未知')
              }}
              · {{ tr('费用未知') }}<span v-if="call.error_code"> · {{ call.error_code }}</span>
            </p>
            <small v-if="call.returned_model">{{
              tr('实际返回模型：{0}', [call.returned_model as string])
            }}</small>
          </li>
        </ol>
        <details v-for="(frame, index) in data.frames" :key="index">
          <summary>
            {{ tr('本轮任务约束') }} ·
            {{ tr(frame.validation_status === 'validated' ? '已验证' : '保留用户原话') }}
          </summary>
          <p>
            {{ tr('用户来源：{0}', [list(frame.source_message_ids).join(tr('、')) || tr('无')]) }}
          </p>
          <ul>
            <li v-for="(constraint, i) in list(frame.constraints)" :key="i">
              {{ constraint.key }} {{ constraint.operator }} {{ constraint.value }}
              {{ constraint.unit }}
              <blockquote>{{ constraint.exact_quote }}</blockquote>
            </li>
          </ul>
          <p v-if="list(frame.unresolved).length" class="notice amber">
            {{ tr('尚待明确：{0}', [list(frame.unresolved).join(tr('；'))]) }}
          </p>
        </details>
        <details v-for="(manifest, index) in data.manifests" :key="index">
          <summary>
            {{
              tr('第 {0} 次上下文选取 · {1} 项来源', [
                index + 1,
                list(manifest.selected_source_ids).length,
              ])
            }}
          </summary>
          <p>
            {{ tr('已采用：{0}', [list(manifest.selected_source_ids).join(tr('、')) || tr('无')]) }}
          </p>
          <ul>
            <li v-for="(item, i) in list(manifest.omitted)" :key="i">
              {{ item.source_id }} · {{ tr(reason[item.reason] || item.reason) }}
            </li>
          </ul>
          <p v-if="manifest.token_budget">
            {{
              tr('输入估算 {0} / 上限 {1} tokens（不是实际计费用量）', [
                object(manifest.token_budget).estimated_input_tokens,
                object(manifest.token_budget).max_input_tokens,
              ])
            }}
          </p>
        </details>
      </template>
      <button class="text-link" :disabled="loading" @click="refresh">{{ tr('刷新记录') }}</button>
    </div>
  </section>
</template>

<style scoped>
.context-inspector {
  padding: 14px 24px;
  border-top: 1px solid var(--line);
}
@media (max-width: 580px) {
  .context-inspector {
    padding-inline: 20px;
  }
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
