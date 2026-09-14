import type { Schema } from '~/types/models'

export function newerWork(left: Schema<'WorkView'>, right: Schema<'WorkView'>) {
  const current = left.version > right.version ? left : right
  if (left.mission_id !== right.mission_id) return current
  const freshest =
    (Date.parse(left.business?.observed_at || '') || 0) >
    (Date.parse(right.business?.observed_at || '') || 0)
      ? left
      : right
  return { ...current, business: freshest.business, mission: freshest.mission }
}

export function workPresentation(item: Schema<'WorkView'>, now = Date.now()) {
  const processing =
    item.status === 'PROCESSING' &&
    item.processing_expires_at &&
    Date.parse(item.processing_expires_at) <= now
      ? '处理中断，等待恢复'
      : {
          RECEIVED: '已收到',
          PROCESSING: '正在处理',
          WAITING_INPUT: '需要你补充',
          RESULT_READY: '结果已出',
          BLOCKED: '需要处理',
          COMPLETED: '本次事项已完成',
          CANCELLED: '本轮处理已停止',
        }[item.status]
  const business = item.business
  if (business) {
    if (business.can_confirm && business.valid_until && Date.parse(business.valid_until) <= now)
      return {
        label: '方案待重新核对',
        detail: '方案或数据有效期已到，请刷新后核对。',
        action: '查看并重新检查',
        tone: 'amber',
        priority: 15,
        processing,
      }
    // A question may need input, but must not hide an unresolved purchase.
    if (business.priority >= 40 && item.status === 'WAITING_INPUT')
      return {
        label: business.label,
        detail: item.question || business.detail,
        action: '补充信息',
        tone: 'amber',
        priority: 30,
        processing,
      }
    return {
      label: business.label,
      detail: business.detail,
      action: business.action_label,
      tone: business.tone,
      priority: business.priority,
      processing,
    }
  }
  if (item.mission)
    return {
      label: '备货状态待核对',
      detail: '打开事项读取当前方案和采购回执。',
      action: '查看备货状态',
      tone: 'gray',
      priority: 35,
      processing,
    }
  return {
    label: processing,
    detail:
      item.question && item.status === 'WAITING_INPUT'
        ? item.question
        : item.summary || '要求已保存，可以继续补充。',
    action: item.status === 'WAITING_INPUT' ? '补充信息' : item.result ? '查看结果' : '继续这件事',
    tone: ['WAITING_INPUT', 'BLOCKED'].includes(item.status) ? 'amber' : 'gray',
    priority: item.status === 'WAITING_INPUT' ? 30 : item.status === 'BLOCKED' ? 32 : 75,
    processing,
  }
}
