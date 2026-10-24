import { backendSettings } from '../utils/backend'
// Readiness only. No credential is sent, so an outage is never confused with an invalid identity.
export default defineEventHandler(async (event) => {
  setHeader(event, 'cache-control', 'no-store')
  try {
    await $fetch(backendSettings(event).url + '/health/ready', { timeout: 3000, retry: 0 })
    return { backend: 'ok' as const }
  } catch {
    // Timeout, refused connection or 503 (database not ready) all mean the backend cannot serve.
    return { backend: 'unreachable' as const }
  }
})
