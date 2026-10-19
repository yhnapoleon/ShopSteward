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
  sourcing?: boolean
  /** How an approved purchase goes out unless its supplier was read from documents. */
  purchase_channel?: 'simulator' | 'assisted'
  quantitySimulation?: boolean
  planRevision: boolean
}
export type PendingApproval = {
  storeId: string
  planId: string
  body: Schema<'PlanDecision'>
  key: string
}
