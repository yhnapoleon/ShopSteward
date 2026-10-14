import { api } from '~/utils/api'

// Which services behind this page are available right now (workspace redesign §11). Each entry
// carries a word for its state; the dot colour only repeats it.

type Probe = 'checking' | 'ready' | 'down'
export type ServiceTone = 'ok' | 'warn' | 'off'
export type ServiceEntry = { id: string; name: string; state: string; tone: ServiceTone }

export function useServiceStatus() {
  const shop = useShop()
  const work = useWorkItems()
  const { s } = shop
  // The forecast service is probed once per store and remembered for the session.
  const forecast = useState<Record<string, Probe>>('service-forecast', () => ({}))
  function probe(storeId: string) {
    if (!storeId || !s.session?.authenticated || forecast.value[storeId]) return
    forecast.value[storeId] = 'checking'
    api(`/api/v1/stores/${encodeURIComponent(storeId)}/forecast/model`)
      .then(() => (forecast.value[storeId] = 'ready'))
      .catch(() => (forecast.value[storeId] = 'down'))
  }
  watch(
    () => [s.storeId, s.session?.authenticated] as const,
    ([id]) => probe(id),
    { immediate: true },
  )
  // A probe that failed while the backend itself was unreachable is retried once it is back.
  watch(
    () => s.connected,
    (connected, before) => {
      if (connected && before === false && forecast.value[s.storeId] === 'down') {
        delete forecast.value[s.storeId]
        probe(s.storeId)
      }
    },
  )
  const services = computed<ServiceEntry[]>(() => {
    const probed = forecast.value[s.storeId]
    return [
      {
        id: 'business',
        name: '业务接口',
        state: s.connected ? '已连接' : s.loading ? '正在连接' : '暂时无法连接',
        tone: s.connected ? 'ok' : s.loading ? 'off' : 'warn',
      },
      {
        id: 'work',
        name: '事项助手',
        state: !s.session?.workIntake
          ? '未接入'
          : work.s.processorAvailable
            ? '可以处理'
            : '暂不可用，要求会先保存',
        tone: !s.session?.workIntake ? 'off' : work.s.processorAvailable ? 'ok' : 'warn',
      },
      {
        id: 'agent',
        name: 'Agent',
        state: s.session?.agentEnabled ? '已启用' : '未启用',
        tone: s.session?.agentEnabled ? 'ok' : 'off',
      },
      {
        id: 'forecast',
        name: '预测服务',
        state: probed === 'ready' ? '运行中' : probed === 'checking' ? '正在检测' : '未启动',
        tone: probed === 'ready' ? 'ok' : 'off',
      },
    ]
  })
  return { services }
}
