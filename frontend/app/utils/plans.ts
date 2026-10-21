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

/**
 * The choices a plan card offers. A recovery plan stands for one adopted quote: confirm it or buy
 * nothing this round. A routine plan offers its recommendation beside 20, 40 and none, largest
 * first and "none" last, so a new recommendation moves the badge, never the options.
 */
export function planOptions(plan: PlanDocument | null | undefined) {
  if (!plan) return []
  if (isRecoveryPlan(plan))
    return plan.candidates.filter((c) => c.id === plan.selected_candidate_id || c.quantity === 0)
  const shown = [plan.proposed_purchase?.quantity || 0, 20, 40, 0]
  return plan.candidates
    .filter(
      (c) =>
        shown.includes(c.quantity) && c.rejection_reasons.every((r) => r === 'TASK_QUANTITY_LIMIT'),
    )
    .sort((a, b) => b.quantity - a.quantity)
}
