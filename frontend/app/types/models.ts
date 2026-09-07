import type { components } from './backend'
export type Schema<K extends keyof components['schemas']> = components['schemas'][K]
export type Session = {
  authenticated: boolean
  principal_id: string
  roles: string[]
  agentEnabled: boolean
  devTools: boolean
  planRevision: boolean
}
export type PendingApproval = {
  storeId: string
  planId: string
  body: Schema<'PlanDecision'>
  key: string
}
