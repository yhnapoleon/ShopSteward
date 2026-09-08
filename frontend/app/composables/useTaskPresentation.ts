import { actionLabel, when } from '~/utils/presentation'
export function useTaskPresentation() {
  const { s, mission, stock, canDecide } = useShop()
  const actions = computed(() => s.actions.filter((a) => a.mission_id === mission.value?.id))
  const pending = computed(() =>
    actions.value.find((a) => ['QUEUED', 'EXECUTING', 'UNKNOWN'].includes(a.status)),
  )
  const status = computed(() => {
    if (!mission.value)
      return { label: '尚未建立', tone: 'gray', group: '待处理', detail: '先交代这次备货目标。' }
    if (mission.value.status === 'COMPLETED')
      return {
        label: '委托已完成',
        tone: 'green',
        group: '已完成',
        detail: '主动跟进已结束，决定与采购记录保留。',
      }
    if (mission.value.status === 'CANCELLED')
      return {
        label: '委托已取消',
        tone: 'gray',
        group: '已结束',
        detail: '已提交的采购仍以实际回执为准。',
      }
    if (s.pending?.storeId === s.storeId)
      return {
        label: '确认结果待核实',
        tone: 'amber',
        group: '待处理',
        detail: '先查询原确认结果，避免重复采购。',
      }
    if (pending.value)
      return {
        label: actionLabel(pending.value.status),
        tone: pending.value.status === 'UNKNOWN' ? 'amber' : 'blue',
        group: '进行中',
        detail: '确认已受理，采购结果以回执为准。',
      }
    if (!s.connected || s.dashboard?.freshness.status !== 'FRESH')
      return {
        label: '数据待同步',
        tone: 'amber',
        group: '待处理',
        detail: '保留上次事实，取得最新数据后再决定。',
      }
    if (mission.value.status === 'PAUSED')
      return {
        label: '主动跟进已暂停',
        tone: 'gray',
        group: '进行中',
        detail: '已提交的订单与到货记录保留。',
      }
    if (
      s.plan?.status === 'PENDING_APPROVAL' &&
      s.dashboard &&
      s.plan.state_version !== s.dashboard.state.state_version
    )
      return {
        label: '方案待更新',
        tone: 'amber',
        group: '待处理',
        detail: '经营事实已变化，等待新的评估结果。',
      }
    if (canDecide.value)
      return {
        label: '等待你确认',
        tone: 'amber',
        group: '待处理',
        detail: '可以先问依据、调整安排，再核对采购。',
      }
    if (s.plan?.status === 'EXPIRED')
      return {
        label: '方案需要更新',
        tone: 'amber',
        group: '待处理',
        detail: '重新检查适用条件，再核对新方案。',
      }
    if (stock.value?.in_transit)
      return {
        label: '等待到货',
        tone: 'blue',
        group: '进行中',
        detail: `${stock.value.in_transit} 件在途，后续到货会更新在这项任务中。`,
      }
    return {
      label: '持续跟进中',
      tone: 'blue',
      group: '进行中',
      detail: '下一次检查：' + when(mission.value.schedule.next_run_at),
    }
  })
  return { status, actions, pending }
}
