export const money = (minor: number | undefined | null) =>
  minor == null
    ? '未取得'
    : new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency: 'CNY',
        maximumFractionDigits: 2,
        minimumFractionDigits: 0,
      }).format(minor / 100)
export const number = (n: number | undefined | null) =>
  n == null ? '未取得' : n.toLocaleString('zh-CN')
export const when = (v: string | undefined | null) =>
  v
    ? new Date(v).toLocaleString('zh-CN', {
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    : '尚未取得'
export const actionLabel = (status: string) =>
  ({
    QUEUED: '等待提交',
    EXECUTING: '正在提交',
    SUCCEEDED: '采购已受理',
    UNKNOWN: '结果待核实',
    FAILED: '未成功',
    STALE: '原方案失效',
    CANCELLED: '已取消',
  })[status] || status
export const reasonLabel = (r: string) =>
  ({
    CASH_FLOOR_VIOLATION: '低于现金底线',
    TASK_QUANTITY_LIMIT: '超过本轮数量上限',
    MINIMUM_ORDER_QUANTITY: '未达到起订量',
    PACK_SIZE_MISMATCH: '不符合包装数量',
    ARRIVAL_WINDOW_MISSED: '不能在需求周期内到货',
  })[r] || r
