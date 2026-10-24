import type { H3Event } from 'h3'
export function sameOrigin(event: H3Event) {
  const origin = getHeader(event, 'origin')
  if (origin && origin !== getRequestURL(event).origin)
    throw createError({ statusCode: 403, statusMessage: 'Cross-origin command refused' })
}
export function backendSettings(event: H3Event) {
  const c = useRuntimeConfig(event)
  const local = ['127.0.0.1', 'localhost', '[::1]'].includes(getRequestURL(event).hostname)
  return {
    url: String(c.backendUrl).replace(/\/$/, ''),
    token:
      getCookie(event, 'shopsteward-session') ||
      (import.meta.dev && local ? String(c.backendToken || '') : ''),
    devTools: String(c.devTools) === 'true',
    agentEnabled: String(c.agentEnabled) === 'true',
  }
}
export async function currentIdentity(event: H3Event) {
  const config = backendSettings(event)
  if (!config.token) throw createError({ statusCode: 401, statusMessage: '请连接后端用户身份' })
  return await $fetch<{
    principal_id: string
    roles: string[]
    store_scope: string
    capabilities?: string[]
  }>(config.url + '/api/v1/me', {
    headers: { Authorization: 'Bearer ' + config.token },
    timeout: 10000,
    retry: 0,
  })
}
