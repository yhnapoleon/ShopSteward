<script setup lang="ts">
import { describeTool } from '~/utils/agent'
import { when } from '~/utils/presentation'
const agent = useAgentConversation()
const { s, status, running, active, inspected, tools } = agent
const emit = defineEmits<{ target: [name: string] }>()
const historical = computed(() => !!s.inspectedRunId && s.inspectedRunId !== s.run?.id)
const failedTools = computed(
  () => tools.value.filter((t) => t.ok === false || t.status === 'INTERRUPTED').length,
)
const duration = (ms: number) => (ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`)
</script>
<template>
  <aside class="agent-workspace glass" aria-label="Agent工作区">
    <header class="agent-workspace-head">
      <div class="agent-monogram"><AppIcon name="sparkles" /></div>
      <div>
        <h2>Agent 工作区</h2>
        <p>过程、依据与任务对话</p>
      </div>
    </header>
    <section class="agent-run-section" aria-label="Agent执行过程">
      <div
        class="agent-run-status"
        :class="{
          'is-running': running,
          'is-attention': s.syncError || ['FAILED', 'WAITING_INPUT'].includes(s.run?.status || ''),
        }"
        role="status"
      >
        <span class="agent-live-dot" /><strong>{{ status }}</strong>
      </div>
      <p class="agent-run-note" v-if="s.syncError">
        {{ s.syncError }}<button class="text-link" @click="agent.load(true)">重新同步</button>
      </p>
      <p v-else-if="s.run?.status === 'RUNNING'" class="agent-run-note">
        {{
          Array.isArray(s.run.activity)
            ? '工具过程持续更新；采购状态以左侧回执为准。'
            : '以下为已经返回的工具记录；本轮可能仍有后续工作。'
        }}
      </p>
      <p v-else-if="s.run?.status === 'FAILED'" class="agent-run-note">
        {{ s.run.error_code || '未取得完整结果' }}。已发生的业务变更以回执为准。
      </p>
      <p v-else-if="s.run?.status === 'SUCCEEDED'" class="agent-run-note">
        回答完成不代表采购完成，实际结果见左侧任务记录。
      </p>
      <p v-else-if="s.run?.status === 'CANCELLED'" class="agent-run-note">
        后续工作已停止；已提交的变更仍保留。
      </p>
      <p v-if="active && Array.isArray(s.run?.activity)" class="agent-stream-note">
        {{
          s.streamStatus === 'live'
            ? '实时更新'
            : s.streamStatus === 'polling'
              ? '实时连接暂不可用，正在定期同步'
              : s.streamStatus === 'connecting'
                ? '正在连接实时进度'
                : '进度已保留'
        }}
      </p>
      <div class="agent-run-controls">
        <button v-if="active" class="text-link" :disabled="s.controlling" @click="agent.cancel">
          停止本轮回答</button
        ><span v-if="s.run?.trigger === 'FOLLOWUP'" class="agent-trigger">经营变化更新</span>
      </div>
      <div v-if="historical" class="agent-history-banner">
        正在回看历史过程<button class="text-link" @click="agent.inspectRun('')">
          返回当前工作
        </button>
      </div>
      <p v-if="s.historyError" class="notice amber">{{ s.historyError }}</p>
      <details
        v-if="inspected"
        class="tool-timeline"
        :open="s.expandedRuns[inspected.id] ?? (active || historical || tools.length < 5)"
        @toggle="s.expandedRuns[inspected.id] = ($event.target as HTMLDetailsElement).open"
        :key="inspected.id"
      >
        <summary>
          <span>{{ historical ? '这一轮' : '工作记录' }} · {{ tools.length }} 条工具记录</span
          ><span v-if="failedTools" class="tool-error-count">{{ failedTools }} 步未成功</span
          ><AppIcon name="chevron-down" />
        </summary>
        <p v-if="!tools.length" class="agent-run-note">
          {{
            ['QUEUED', 'RUNNING'].includes(inspected.status)
              ? '尚无工具结果返回。'
              : '这一轮没有可展示的工具记录。'
          }}
        </p>
        <ol>
          <li
            v-for="(tool, index) in tools"
            :key="inspected.id + ':' + tool.invocation_id"
            :data-invocation="tool.invocation_id"
            :class="{
              failed: tool.ok === false,
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
                            : tool.ok === false
                              ? 'circle-alert'
                              : 'clock'
                    " /></span
                ><span class="tool-step-name"
                  >{{ describeTool(tool.tool).title
                  }}<small>{{ describeTool(tool.tool).kind }}</small></span
                ><span class="tool-state">{{
                  tool.status === 'RUNNING'
                    ? '进行中'
                    : tool.status === 'INTERRUPTED'
                      ? '已中断'
                      : tool.ok === true
                        ? '已完成'
                        : tool.ok === false
                          ? '未成功'
                          : '已返回'
                }}</span>
              </summary>
              <div class="tool-step-content">
                <p v-if="tool.duration_ms != null">
                  本次耗时 {{ duration(tool.duration_ms)
                  }}<span v-if="(tool.attempt || 1) > 1"> · 第 {{ tool.attempt }} 次尝试</span>
                </p>
                <p v-if="tool.status === 'INTERRUPTED'">此步已中断；已发生的变更以业务记录为准。</p>
                <p v-if="tool.error_code">{{ tool.error_code }}</p>
                <p v-if="tool.tool === 'evaluate_plan'">只试算，不等于方案已修改或采购已提交。</p>
                <p v-if="tool.tool === 'revise_plan'">
                  修订结果以实际方案版本为准，采购仍需单独确认。
                </p>
                <p v-if="tool.tool === 'request_check'">
                  请求受理与检查完成分别记录，请查看后续业务结果。
                </p>
                <button
                  v-if="!historical && describeTool(tool.tool).target"
                  class="text-link"
                  @click="emit('target', describeTool(tool.tool).target!)"
                >
                  查看对应{{ describeTool(tool.tool).target === 'facts' ? '经营数据' : '任务内容'
                  }}<AppIcon name="arrow-up-right" /></button
                ><AgentReferences :references="tool.references" :run-id="inspected.id" />
                <details class="tool-technical">
                  <summary>调用标识 · 第 {{ index + 1 }} 步</summary>
                  <code>{{ tool.tool }}<br />{{ tool.invocation_id }}</code>
                </details>
              </div>
            </details>
          </li>
        </ol>
        <p class="agent-run-meta">
          {{ when(inspected.created_at)
          }}<template v-if="inspected.finished_at">
            · 结束于 {{ when(inspected.finished_at) }}</template
          >
        </p>
      </details>
    </section>
    <section v-if="inspected?.outcomes?.length" class="agent-outcomes" aria-label="本轮业务成果">
      <h3>{{ historical ? '历史业务成果' : '本轮业务成果' }}</h3>
      <AgentOutcome
        v-for="o in inspected.outcomes"
        :key="inspected.id + o.invocation_id"
        :outcome="o"
      />
    </section>
    <AgentConversation />
  </aside>
</template>
