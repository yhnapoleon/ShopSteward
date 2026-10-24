import type { H3Event } from 'h3'

// This path uses a streaming response, not the buffering JSON proxy.
export async function agentProgressStream(event: H3Event, url: string, token: string) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  event.node.res.once('close', abort)
  const timeout = setTimeout(abort, 10000)
  try {
    const headers: Record<string, string> = {
      Authorization: 'Bearer ' + token,
      Accept: 'text/event-stream',
    }
    const cursor = getHeader(event, 'last-event-id')
    if (cursor) headers['Last-Event-ID'] = cursor
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(getQuery(event)))
      if (typeof value === 'string') query.set(key, value)
    const response = await fetch(url + '?' + query, { headers, signal: controller.signal })
    clearTimeout(timeout)
    setResponseStatus(event, response.status)
    if (!response.ok) return await response.json()
    if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream'))
      throw new Error('Invalid progress response')
    setHeader(event, 'content-type', 'text/event-stream; charset=utf-8')
    setHeader(event, 'cache-control', 'no-store')
    setHeader(event, 'x-accel-buffering', 'no')
    return await sendStream(event, response.body)
  } catch {
    if (event.node.res.headersSent || event.node.res.destroyed) return
    setResponseStatus(event, 502)
    return {
      error: {
        code: 'PROGRESS_UNAVAILABLE',
        message: '进度连接暂不可用，请同步任务状态。',
        retryable: true,
      },
    }
  } finally {
    clearTimeout(timeout)
    event.node.res.off('close', abort)
    controller.abort()
  }
}
