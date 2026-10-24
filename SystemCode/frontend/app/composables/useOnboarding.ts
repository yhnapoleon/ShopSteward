type TourStatus = 'new' | 'active' | 'paused' | 'skipped' | 'completed'
type TourProgress = {
  status: TourStatus
  step: number
  storeId: string
  resultId: string
  resultOpened: boolean
  simulationSkipped: boolean
}
const fresh = (): TourProgress => ({
  status: 'new',
  step: 0,
  storeId: '',
  resultId: '',
  resultOpened: false,
  simulationSkipped: false,
})

/** Browser-only learning progress. It never grants permission or submits business actions. */
export function useOnboarding() {
  const s = useState('onboarding', () => ({
    ...fresh(),
    principal: '',
    initialized: false,
    storageFailed: false,
    completedNow: false,
    storeChanged: false,
  })).value
  const key = () => 'shopsteward.onboarding.v1:' + encodeURIComponent(s.principal)
  function save() {
    if (!s.principal) return
    try {
      const { status, step, storeId, resultId, resultOpened, simulationSkipped } = s
      localStorage.setItem(
        key(),
        JSON.stringify({
          status,
          step,
          storeId,
          resultId,
          resultOpened,
          simulationSkipped,
        }),
      )
      s.storageFailed = false
    } catch {
      s.storageFailed = true
    }
  }
  function initialize(principal: string) {
    if (s.initialized && s.principal === principal) return
    Object.assign(s, fresh(), {
      principal,
      initialized: true,
      completedNow: false,
      storageFailed: false,
      storeChanged: false,
    })
    if (!principal) return
    try {
      const value = JSON.parse(localStorage.getItem(key()) || 'null')
      if (
        value &&
        ['new', 'active', 'paused', 'skipped', 'completed'].includes(value.status) &&
        Number.isInteger(value.step) &&
        value.step >= 0 &&
        value.step <= 5 &&
        typeof value.storeId === 'string' &&
        typeof value.resultId === 'string'
      ) {
        Object.assign(s, {
          status: value.status === 'active' ? 'paused' : value.status,
          step: value.step,
          storeId: value.storeId,
          resultId: value.resultId,
          resultOpened: false,
          simulationSkipped: value.simulationSkipped === true,
        })
      }
    } catch {
      s.storageFailed = true
    }
  }
  function syncStore(id: string) {
    if (!s.initialized || !id || s.storeId === id) return
    if (s.storeId) {
      s.resultId = ''
      s.resultOpened = false
      s.simulationSkipped = false
      if (['active', 'paused'].includes(s.status)) {
        s.step = 1
        s.storeChanged = true
      }
    }
    s.storeId = id
    save()
  }
  function start() {
    s.status = 'active'
    s.step = 1
    s.resultOpened = false
    s.completedNow = false
    s.storeChanged = false
    save()
  }
  function go(step: number) {
    s.step = Math.max(1, Math.min(5, step))
    s.storeChanged = false
    save()
  }
  function recordResult(id: string, store: string) {
    if (s.status !== 'active' || s.step !== 3 || store !== s.storeId) return
    s.resultId = id
    s.resultOpened = false
    s.simulationSkipped = false
    go(4)
  }
  function openedResult(id: string, store: string) {
    if (s.status === 'active' && s.step === 5 && id === s.resultId && store === s.storeId) {
      s.resultOpened = true
      save()
    }
  }
  function pause() {
    s.status = 'paused'
    save()
  }
  function resume() {
    s.status = 'active'
    if (!s.step) s.step = 1
    save()
  }
  function skip() {
    s.status = 'skipped'
    s.completedNow = false
    save()
  }
  function skipSimulation() {
    s.resultId = ''
    s.resultOpened = false
    s.simulationSkipped = true
    go(4)
  }
  function finish() {
    s.status = 'completed'
    s.completedNow = true
    save()
  }
  function replay() {
    s.status = 'new'
    s.step = 0
    s.resultOpened = false
    s.simulationSkipped = false
    s.completedNow = false
    save()
  }
  function forgetResult() {
    s.resultId = ''
    s.resultOpened = false
    s.simulationSkipped = false
    go(3)
  }
  return {
    s,
    initialize,
    syncStore,
    start,
    go,
    recordResult,
    openedResult,
    pause,
    resume,
    skip,
    skipSimulation,
    finish,
    replay,
    forgetResult,
  }
}
