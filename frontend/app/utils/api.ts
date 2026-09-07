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
  STATE_VERSION_CONFLICT: '经营状态已变化，请查看新方案再确认。',
  PLAN_INPUT_STALE: '方案依据已变化，请重新检查。',
  PLAN_VERSION_CONFLICT: '方案版本已变化，请重新核对。',
  PLAN_ALREADY_DECIDED: '这份方案已被处理，正在取得最新结果。',
  PLAN_EXPIRED: '方案已过期，请重新检查。',
  DATA_STALE: '数据还未同步完成，暂时不能采购。',
  ACTION_IN_PROGRESS: '已有采购待核实，请先查看原动作。',
  MISSION_NOT_ACTIVE: '任务已暂停或结束，不能提交采购。',
  CASH_FLOOR_VIOLATION: '采购会低于现金底线，不能执行。',
  AGENT_NOT_CONFIGURED: 'Agent暂未启用。经营查询与采购仍可使用。',
  FORBIDDEN: '当前身份没有执行此操作的权限。',
  UNAUTHENTICATED: '后端身份不可用，请重新连接。',
  NO_PURCHASE_PROPOSED: '当前方案不需要采购。',
}
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
    throw new ApiFailure(
      error?.code || 'CONNECTION_ERROR',
      messages[error?.code || ''] ||
        error?.message ||
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
