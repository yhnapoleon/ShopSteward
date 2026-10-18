import type { PlanDocument, Schema } from '~/types/models'

export function isRecoveryPlan(
  plan: PlanDocument | null | undefined,
): plan is Schema<'RecoveryPlan'> {
  return !!plan && 'plan_kind' in plan && plan.plan_kind === 'recovery_v1'
}

// Quantities are unique only in baseline plans. Recovery quotes can share a
// quantity while differing in supplier, cash, ETA and lost demand.
export function selectedPlanCandidate(plan: PlanDocument | null | undefined, quantity: number) {
  if (!plan) return undefined
  if (isRecoveryPlan(plan) && quantity !== 0)
    return plan.candidates.find(
      (candidate) => candidate.id === plan.selected_candidate_id && candidate.quantity === quantity,
    )
  return plan.candidates.find((candidate) => candidate.quantity === quantity)
}
