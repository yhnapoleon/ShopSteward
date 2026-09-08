import { backendRoutes } from '../../utils/backend-routes'
import { backendSettings, sameOrigin } from '../../utils/backend'
import { isKnowledgeTransfer, knowledgeTransfer } from '../../utils/knowledge-transfer'
export default defineEventHandler(async (event) => {
  const config = backendSettings(event)
  const path = '/' + getRouterParam(event, 'path')
  const method = getMethod(event)
  const allowed = backendRoutes.some(
    ([verb, pattern]) =>
      verb === method &&
      new RegExp('^' + pattern.replace(/\{[^}]+\}/g, '[A-Za-z0-9_-]+') + '$').test(path),
  )
  if (!allowed || (path.startsWith('/dev/') && !config.devTools))
    throw createError({ statusCode: 404, statusMessage: 'Unknown operation' })
  if (!config.token) throw createError({ statusCode: 401, statusMessage: '请连接后端用户身份' })
  if (isKnowledgeTransfer(method, path)) return knowledgeTransfer(event, path)
  const headers: Record<string, string> = { Authorization: 'Bearer ' + config.token }
  let body: string | undefined
  if (method !== 'GET') {
    sameOrigin(event)
    if (!getHeader(event, 'content-type')?.startsWith('application/json'))
      throw createError({ statusCode: 415, statusMessage: 'JSON required' })
    headers['Content-Type'] = 'application/json'
    const key = getHeader(event, 'idempotency-key')
    if (key) headers['Idempotency-Key'] = key
    body = await readRawBody(event)
    if (body && body.length > 256_000)
      throw createError({ statusCode: 413, statusMessage: 'Request too large' })
  }
  try {
    const response = await $fetch.raw(config.url + path, {
      method: method as 'GET' | 'POST' | 'PATCH',
      headers,
      body,
      query: getQuery(event),
      timeout: 20000,
      retry: 0,
      ignoreResponseError: true,
    })
    setResponseStatus(event, response.status)
    const requestId = response.headers.get('x-request-id')
    if (requestId) setHeader(event, 'x-request-id', requestId)
    setHeader(event, 'cache-control', 'no-store')
    return response._data
  } catch {
    setResponseStatus(event, 502)
    return {
      error: {
        code: 'BACKEND_UNAVAILABLE',
        message: '后端没有返回结果；采购请求可能已经受理，请核实原动作。',
        retryable: true,
      },
    }
  }
})
