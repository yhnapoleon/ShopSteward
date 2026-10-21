<script setup lang="ts">
import { joinText, t as tr } from '~/i18n'
import { describeTool } from '~/utils/agent'
import { when } from '~/utils/presentation'
import ContextInspector from '~/components/ContextInspector.vue'
const agent = useAgentConversation()
const { s, status, running, active, inspected, tools } = agent
const { hasRole } = useShop()
const demo = useDemoMode()
const emit = defineEmits<{ target: [name: string] }>()
const historical = computed(() => !!s.inspectedRunId && s.inspectedRunId !== s.run?.id)
type Tool = (typeof tools.value)[number]
// The tool ran but the data it reads does not exist yet (no forecast has been run): said in
// grey, not counted as a failure.
const noData = new Set(['FORECAST_UNAVAILABLE', 'FORECAST_NOT_FOUND', 'EVIDENCE_UNAVAILABLE'])
const empty = (t: Tool) => t.ok === false && noData.has(t.error_code || '')
const failedTools = computed(
  () =>
    tools.value.filter((t) => (t.ok === false && !empty(t)) || t.status === 'INTERRUPTED').length,
)
const duration = (ms: number) => (ms < 100 ? '<0.1s' : `${(ms / 1000).toFixed(1)}s`)
// The activity log opens while the run works, for short lists and for history. A list this view
// saw working stays as it was when the answer arrives; only the owner's own choice is kept.
const watched = reactive(new Set<string>())
watch(
  () => [inspected.value?.id, active.value] as const,
  ([id, on]) => {
    if (id && on) watched.add(id)
  },
  { immediate: true },
)
const openByDefault = computed(
  () =>
    !!inspected.value &&
    (active.value || historical.value || tools.value.length < 5 || watched.has(inspected.value.id)),
)
function toggled(id: string, open: boolean) {
  if (open === openByDefault.value) delete s.expandedRuns[id]
  else s.expandedRuns[id] = open
}
</script>
<template>
  <aside class="agent-workspace glass" :aria-label="tr('Agent工作区')">
    <section class="agent-run-section" :aria-label="tr('Agent执行过程')">
      <div
        class="agent-run-status"
        :class="{
          'is-running': running,
          'is-attention': s.syncError || ['FAILED', 'WAITING_INPUT'].includes(s.run?.status || ''),
        }"
        role="status"
      >
        <span class="agent-live-dot" /><strong>{{ tr(status) }}</strong>
      </div>
      <p class="agent-run-note" v-if="s.syncError">
        {{ tr(s.syncError)
        }}<button class="text-link" @click="agent.load(true)">{{ tr('重新同步') }}</button>
      </p>
      <p v-else-if="s.run?.status === 'FAILED'" class="agent-run-note">
        {{ tr('{0}。已发生的业务变更以回执为准。', [tr(s.run.error_code || '未取得完整结果')]) }}
      </p>
      <p v-else-if="s.run?.status === 'CANCELLED'" class="agent-run-note">
        {{ tr('后续工作已停止；已提交的变更仍保留。') }}
      </p>
      <p v-if="active && Array.isArray(s.run?.activity)" class="agent-stream-note">
        {{
          tr(
            s.streamStatus === 'live'
              ? '实时更新'
              : s.streamStatus === 'polling'
                ? '实时连接暂不可用，正在定期同步'
                : s.streamStatus === 'connecting'
                  ? '正在连接实时进度'
                  : '进度已保留',
          )
        }}
      </p>
      <div class="agent-run-controls">
        <button v-if="active" class="text-link" :disabled="s.controlling" @click="agent.cancel">
          {{ tr('停止本轮回答') }}</button
        ><span v-if="s.run?.trigger === 'FOLLOWUP'" class="agent-trigger">{{
          tr('经营变化更新')
        }}</span
        ><button
          v-if="s.conversation && hasRole('operator')"
          class="text-link agent-follow"
          :disabled="s.controlling"
          @click="agent.toggleFollowup"
        >
          {{
            joinText([
              tr('Agent主动解读：'),
              tr(s.conversation.followup_enabled ? '已开启' : '未开启'),
            ])
          }}
        </button>
      </div>
      <div v-if="historical" class="agent-history-banner">
        {{ tr('正在回看历史过程')
        }}<button class="text-link" @click="agent.inspectRun('')">{{ tr('返回当前工作') }}</button>
      </div>
      <p v-if="s.historyError" class="notice amber">{{ tr(s.historyError) }}</p>
      <details
        v-if="inspected"
        class="tool-timeline"
        :open="s.expandedRuns[inspected.id] ?? openByDefault"
        @toggle="toggled(inspected.id, ($event.target as HTMLDetailsElement).open)"
        :key="inspected.id"
      >
        <summary>
          <span>{{
            joinText([
              tr(historical ? '这一轮' : '工作记录'),
              '·',
              tools.length === 1 ? tr('1条工具记录') : tr('{0}条工具记录', [tools.length]),
            ])
          }}</span
          ><span v-if="failedTools" class="tool-error-count">{{
            failedTools === 1 ? tr('1 步未成功') : tr('{0} 步未成功', [failedTools])
          }}</span
          ><AppIcon name="chevron-down" />
        </summary>
        <p v-if="!tools.length" class="agent-run-note">
          {{
            tr(
              ['QUEUED', 'RUNNING'].includes(inspected.status)
                ? '尚无工具结果返回。'
                : '这一轮没有可展示的工具记录。',
            )
          }}
        </p>
        <ol>
          <li
            v-for="(tool, index) in tools"
            :key="inspected.id + ':' + tool.invocation_id"
            :data-invocation="tool.invocation_id"
            :class="{
              failed: tool.ok === false && !empty(tool),
              'tool-empty': empty(tool),
              'tool-interrupted': tool.status === 'INTERRUPTED',
              'tool-running':
                tool.status === 'RUNNING' &&
                running &&
                !historical &&
                tool.invocation_id === agent.currentTool.value?.invocation_id,
            }"
          >
            <details>
              <summary>
                <span class="tool-step-icon"
                  ><AppIcon
                    :name="
                      tool.status === 'RUNNING'
                        ? 'loader-circle'
                        : tool.status === 'INTERRUPTED'
                          ? 'pause'
                          : tool.ok === true
                            ? 'check'
                            : empty(tool)
                              ? 'info'
                              : tool.ok === false
                                ? 'circle-alert'
                                : 'clock'
                    " /></span
                ><span class="tool-step-name"
                  >{{ tr(describeTool(tool.tool).title)
                  }}<small>{{ tr(describeTool(tool.tool).kind) }}</small></span
                ><span class="tool-state">{{
                  tr(
                    tool.status === 'RUNNING'
                      ? '进行中'
                      : tool.status === 'INTERRUPTED'
                        ? '已中断'
                        : tool.ok === true
                          ? '已完成'
                          : empty(tool)
                            ? '暂无数据'
                            : tool.ok === false
                              ? '未成功'
                              : '已返回',
                  )
                }}</span
                ><span v-if="tool.duration_ms != null" class="tool-duration"
                  >· {{ duration(tool.duration_ms) }}</span
                >
              </summary>
              <div class="tool-step-content">
                <p v-if="(tool.attempt || 1) > 1">{{ tr('第 {0} 次尝试', [tool.attempt!]) }}</p>
                <p v-if="tool.status === 'INTERRUPTED'">
                  {{ tr('此步已中断；已发生的变更以业务记录为准。') }}
                </p>
                <p v-if="tool.error_code && !empty(tool)">{{ tr(tool.error_code) }}</p>
                <p v-if="tool.tool === 'evaluate_plan'">
                  {{ tr('只试算，不等于方案已修改或采购已提交。') }}
                </p>
                <p v-if="tool.tool === 'revise_plan'">
                  {{ tr('修订结果以实际方案版本为准，采购仍需单独确认。') }}
                </p>
                <p v-if="tool.tool === 'request_check'">
                  {{ tr('请求受理与检查完成分别记录，请查看后续业务结果。') }}
                </p>
                <button
                  v-if="!historical && describeTool(tool.tool).target"
                  class="text-link"
                  @click="emit('target', describeTool(tool.tool).target!)"
                >
                  {{
                    joinText([
                      tr('查看对应'),
                      tr(describeTool(tool.tool).target === 'facts' ? '经营数据' : '任务内容'),
                    ])
                  }}<AppIcon name="arrow-up-right" /></button
                ><AgentReferences :references="tool.references" :run-id="inspected.id" />
                <details v-if="!demo.enabled.value" class="tool-technical">
                  <summary>{{ tr('调用标识 · 第 {0} 步', [index + 1]) }}</summary>
                  <code>{{ tr(tool.tool) }}<br />{{ tr(tool.invocation_id) }}</code>
                </details>
              </div>
            </details>
          </li>
        </ol>
        <p class="agent-run-meta">
          {{ tr(when(inspected.created_at))
          }}<template v-if="inspected.finished_at">{{
            joinText([tr('· 结束于'), tr(when(inspected.finished_at))])
          }}</template>
        </p>
      </details>
    </section>
    <section
      v-if="inspected?.outcomes?.length"
      class="agent-outcomes"
      :aria-label="tr('本轮业务成果')"
    >
      <h3>{{ tr(historical ? '历史业务成果' : '本轮业务成果') }}</h3>
      <AgentOutcome
        v-for="o in inspected.outcomes"
        :key="inspected.id + o.invocation_id"
        :outcome="o"
      />
    </section>
    <ContextInspector
      v-if="inspected?.graph_version === 'agent-context-v1' && !demo.enabled.value"
      :key="inspected.id"
      :run-id="inspected.id"
    />
    <AgentConversation />
  </aside>
</template>
