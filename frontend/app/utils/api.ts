export class ApiFailure extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public requestId = '',
  ) {
    super(message)
  }
}
const messages: Record<string, string> = {
  LEARNING_CONTEXT_CHANGED: '本次引用的经验已撤销或依据发生变化，请重新发起请求。',
  LEARNING_QUALITY_REQUIRED: '质量证据尚未满足启用条件，请查看质量卡。',
  LEARNING_FORGOTTEN: '这项经验或其来源已被忘记，不能继续使用。',
  STATE_VERSION_CONFLICT: '经营状态已变化，请查看新方案再确认。',
  PLAN_INPUT_STALE: '方案依据已变化，请重新检查。',
  PLAN_VERSION_CONFLICT: '方案版本已变化，请重新核对。',
  PLAN_ALREADY_DECIDED: '这份方案已被处理，正在取得最新结果。',
  PLAN_EXPIRED: '方案已过期，请重新检查。',
  DATA_STALE: '数据还未同步完成，暂时不能采购。',
  ACTION_IN_PROGRESS: '已有采购待核实，请先查看原动作。',
  ACTION_NOT_WAITING: '这笔订单已不在等待供应商回复，正在取得最新状态。',
  MISSION_NOT_ACTIVE: '任务已暂停或结束，不能提交采购。',
  CASH_FLOOR_VIOLATION: '采购会低于现金底线，不能执行。',
  AGENT_NOT_CONFIGURED: 'Agent暂未启用。经营查询与采购仍可使用。',
  FORBIDDEN: '当前身份没有执行此操作的权限。',
  UNAUTHENTICATED: '后端身份不可用，请重新连接。',
  NO_PURCHASE_PROPOSED: '当前方案不需要采购。',
  // Order writes (execution/assisted.py).
  PARTIAL_SUPPLY_NOT_OFFERED: '这笔订单已经不是“对方只给一部分”的状态，正在取得最新状态。',
  GOODS_QUANTITY_CONFLICT: '到货件数超过这笔订单还没到的数量，请按实际到货重新登记。',
  ARRIVAL_NOT_EXPECTED: '这笔订单现在不用登记到货：只有供应商已确认、由你发出的订单才需要。',
  IDEMPOTENCY_KEY_REUSED: '这次提交和上一次的内容不同，请刷新后再试。',
  // A stored emergency plan the backend cannot read back while it waits (work_items/business.py).
  INVALID_STORED_DATA: '这件事的方案正等待确认，刷新前先确认或拒绝它。',
  FORECAST_NOT_FOUND: '这件商品还没有预测。',
  // What an emergency plan was worked out on changed before it was adopted or confirmed
  // (planning/recovery/validation.py): it is worked out again on the current facts.
  MISSION_VERSION_CONFLICT: '备货委托的设置刚变了，重新比价后再采用。',
  OFFER_VERSION_CONFLICT: '供应商的报价刚变了，重新比价后再采用。',
  INBOUND_VERSION_CONFLICT: '在途订单刚有变化，重新比价后再采用。',
  FORECAST_VERSION_CONFLICT: '需求预测刚有变化，重新比价后再采用。',
  RECOVERY_INTENT_STALE: '这份应急方案已经不是当前方案，请重新比价。',
}
/** A message that is only the code itself (no sentence was sent) says what happened instead. */
const bare = /^[A-Z][A-Z0-9_]+$/
export async function api<T>(
  path: string,
  method: 'GET' | 'POST' | 'PATCH' = 'GET',
  body?: unknown,
  key?: string,
): Promise<T> {
  try {
    return (await $fetch<T>('/api/backend' + path, {
      method,
      body: body as Record<string, unknown> | undefined,
      headers: method === 'GET' ? undefined : { 'Idempotency-Key': key || crypto.randomUUID() },
      retry: 0,
      timeout: 25000,
    })) as T
  } catch (e: unknown) {
    const f = e as {
      statusCode?: number
      status?: number
      data?: {
        error?: { code?: string; message?: string; request_id?: string }
        statusMessage?: string
      }
    }
    const error = f.data?.error
    const sent = error?.message && !bare.test(error.message) ? error.message : ''
    throw new ApiFailure(
      error?.code || 'CONNECTION_ERROR',
      messages[error?.code || ''] ||
        sent ||
        (error?.code ? '暂时没能完成，稍后再试。' : '') ||
        f.data?.statusMessage ||
        '连接中断，未能取得最新结果。',
      f.statusCode || f.status || 0,
      error?.request_id,
    )
  }
}
export function query(params: Record<string, string | number | undefined | null>) {
  return (
    '?' +
    new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== null)
        .map(([k, v]) => [k, String(v)]),
    )
  )
}
