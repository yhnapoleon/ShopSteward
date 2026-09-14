import { currentIdentity, backendSettings } from '../utils/backend'
export default defineEventHandler(async (event) => {
  setHeader(event, 'cache-control', 'no-store')
  const config = backendSettings(event)
  try {
    const identity = await currentIdentity(event)
    const runtime = identity.capabilities
      ? null
      : await $fetch<{ paths: Record<string, unknown> }>(config.url + '/openapi.json', {
          timeout: 5000,
          retry: 0,
        }).catch(() => null)
    return {
      quantitySimulation: Boolean(identity.capabilities?.includes('quantity_simulation')),
      workIntake: identity.capabilities
        ? identity.capabilities.includes('work_intake')
        : Boolean(runtime?.paths['/api/v1/work-items']),
      planRevision: identity.capabilities
        ? identity.capabilities.includes('plan_revision')
        : Boolean(runtime?.paths['/api/v1/plans/{plan_id}/revision']),
      authenticated: true,
      ...identity,
      agentEnabled: config.agentEnabled,
      devTools: config.devTools && identity.roles.includes('admin'),
    }
  } catch {
    return {
      quantitySimulation: false,
      workIntake: false,
      planRevision: false,
      authenticated: false,
      roles: [],
      principal_id: '',
      agentEnabled: false,
      devTools: false,
    }
  }
})
