export type ToolRecord = {
  tool: string
  invocation_id: string
  ok: boolean | null
  references: unknown[]
}
type ToolDescription = { title: string; done: string; kind: string; target?: string }
const catalog: Record<string, ToolDescription> = {
  get_dashboard: {
    title: '核对现金、库存与在途',
    done: '经营数据已读取',
    kind: '读取',
    target: 'facts',
  },
  get_mission: { title: '读取备货委托', done: '委托已读取', kind: '读取', target: 'mission' },
  get_plan: { title: '读取当前方案', done: '方案已读取', kind: '读取', target: 'plan' },
  evaluate_plan: { title: '试算另一种采购安排', done: '试算已完成', kind: '仅试算' },
  revise_plan: {
    title: '修订待确认方案',
    done: '方案修订已返回',
    kind: '方案修订',
    target: 'plan',
  },
  search_documents: { title: '检索文档依据', done: '文档检索已完成', kind: '读取' },
  read_document_evidence: { title: '展开文档证据', done: '证据读取已完成', kind: '读取' },
  memory_edit: { title: '更新偏好', done: '偏好更新已返回', kind: '偏好更新' },
  request_check: {
    title: '请求重新检查',
    done: '检查请求已提交',
    kind: '请求检查',
    target: 'mission',
  },
  read_sales_summary: {
    title: '查看销售汇总',
    done: '销售汇总已读取',
    kind: '读取',
    target: 'facts',
  },
  read_timeline: { title: '查看经营记录', done: '经营记录已读取', kind: '读取', target: 'history' },
  read_experiences: { title: '查看历史经验', done: '历史经验已读取', kind: '读取' },
  get_action: { title: '核对采购状态', done: '采购状态已读取', kind: '读取', target: 'receipt' },
}
export function describeTool(name: string): ToolDescription {
  return catalog[name] || { title: '执行步骤', done: '步骤已返回', kind: '工具调用' }
}
export function sourceIdentity(value: unknown) {
  return JSON.stringify(value)
}
export function sourceLabel(value: unknown) {
  if (!value || typeof value !== 'object') return '来源记录'
  const r = value as Record<string, unknown>
  if (r.type === 'document' || r.kind === 'document' || r.chunk_id) return '文档来源'
  const kind = String(r.type || r.kind || '')
  return (
    (
      {
        plan: '方案',
        mission: '任务',
        state: '经营状态',
        action: '采购记录',
        forecast: '需求假设',
        knowledge: '偏好记录',
      } as Record<string, string>
    )[kind] || '业务来源'
  )
}
