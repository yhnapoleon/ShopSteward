import type { components } from './backend'
export type Schema<K extends keyof components['schemas']> = components['schemas'][K]
export type PlanDocument = Schema<'Plan'> | Schema<'RecoveryPlan'>
export type Session = {
  authenticated: boolean
  principal_id: string
  roles: string[]
  agentEnabled: boolean
  devTools: boolean
  workIntake?: boolean
  recoveryCases?: boolean
  planRevision: boolean
}
export type PendingApproval = {
  storeId: string
  planId: string
  body: Schema<'PlanDecision'>
  key: string
}
