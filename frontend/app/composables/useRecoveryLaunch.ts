import type { RecoveryLaunch } from '~/utils/recovery'

// One request to open the emergency restock flow, from wherever the need shows up: the work page
// header, a reminder, the today page or an order the supplier declined. The flow on the mission's
// work page takes the request and opens its brief; the header reads whether one is in progress.

/**
 * What an in-progress restock shows itself, so the page does not repeat it: its plan, the order
 * its card is handling (sending, replying, receiving), and every purchase it led to (their
 * arrivals are recorded in the card, which knows when recording one ends the restock).
 */
type Owned = { planId: string | null; actionId: string | null; actionIds?: string[] }

export function useRecoveryLaunch() {
  const state = useState('recovery-launch', () => ({
    request: null as RecoveryLaunch | null,
    /** Missions whose emergency restock is in progress, as the flow on the work page sees it. */
    inProgress: {} as Record<string, boolean>,
    /** The plan and orders an in-progress restock shows itself, so the page does not repeat them. */
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
  /** Whether an in-progress restock of this mission holds this order (records its arrival). */
  const holds = (missionId: string | null | undefined, actionId: string) =>
    !!owned(missionId)?.actionIds?.includes(actionId)
  return { state, request, take, report, inProgress, own, owned, holds }
}
