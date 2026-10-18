import type { RecoveryLaunch } from '~/utils/recovery'

// One request to open the emergency restock flow, from wherever the need shows up: the work page
// header, a reminder, the today page or an order the supplier declined. The flow on the mission's
// work page takes the request and opens its brief; the header reads whether one is in progress.

type Owned = { planId: string | null; actionId: string | null; lapsed: boolean }

export function useRecoveryLaunch() {
  const state = useState('recovery-launch', () => ({
    request: null as RecoveryLaunch | null,
    /** Missions whose emergency restock is in progress, as the flow on the work page sees it. */
    inProgress: {} as Record<string, boolean>,
    /** The plan and order an in-progress restock shows itself, so the page does not repeat them;
     * lapsed: the plan it adopted ran out or a regular check replaced it. */
    owned: {} as Record<string, Owned | null>,
  }))
  function request(launch: Omit<RecoveryLaunch, 'at'>) {
    state.value.request = { ...launch, at: Date.now() }
  }
  /** The flow of this mission takes the pending request, once. */
  function take(missionId: string) {
    const pending = state.value.request
    if (!pending || pending.missionId !== missionId) return null
    state.value.request = null
    return pending
  }
  function report(missionId: string, inProgress: boolean) {
    state.value.inProgress[missionId] = inProgress
  }
  const inProgress = (missionId: string | null | undefined) =>
    !!missionId && !!state.value.inProgress[missionId]
  function own(missionId: string, ids: Owned | null) {
    state.value.owned[missionId] = ids
  }
  const owned = (missionId: string | null | undefined) =>
    (missionId && state.value.owned[missionId]) || null
  return { state, request, take, report, inProgress, own, owned }
}
