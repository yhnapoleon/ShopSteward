import type { H3Event } from 'h3'
import { backendSettings, sameOrigin } from './backend'

const uploadPath =
  /^\/api\/v1\/(stores\/[A-Za-z0-9_-]+\/documents|documents\/[A-Za-z0-9_-]+\/versions)$/
const downloadPath = /^\/api\/v1\/documents\/[A-Za-z0-9_-]+\/versions\/[A-Za-z0-9_-]+\/content$/
const maxBodyBytes = 20 * 1024 * 1024 + 128 * 1024

export function isKnowledgeTransfer(method: string, path: string) {
  return (
    (method === 'POST' && uploadPath.test(path)) || (method === 'GET' && downloadPath.test(path))
  )
}

// Only registered K1 file operations use this transport. Other API behavior is unchanged.
export async function knowledgeTransfer(event: H3Event, path: string) {
  const config = backendSettings(event)
  const method = getMethod(event)
  const headers: Record<string, string> = { Authorization: 'Bearer ' + config.token }
  let body: Uint8Array<ArrayBuffer> | undefined
  if (method === 'POST') {
    sameOrigin(event)
    const contentType = getHeader(event, 'content-type') || ''
    if (!/^multipart\/form-data\s*;/i.test(contentType))
      throw createError({ statusCode: 415, statusMessage: '请选择文件上传' })
    const key = getHeader(event, 'idempotency-key')
    if (!key || key.length > 128)
      throw createError({ statusCode: 400, statusMessage: '缺少有效的提交标识' })
    if (Number(getHeader(event, 'content-length')) > maxBodyBytes)
      throw createError({ statusCode: 413, statusMessage: '文件不能超过20 MiB' })
    const chunks: Uint8Array[] = []
    let bytes = 0
    for await (const chunk of event.node.req) {
      const buffer =
        typeof chunk === 'string' ? new TextEncoder().encode(chunk) : new Uint8Array(chunk)
      bytes += buffer.length
      if (bytes > maxBodyBytes)
        throw createError({ statusCode: 413, statusMessage: '文件不能超过20 MiB' })
      chunks.push(buffer)
    }
    body = new Uint8Array(bytes)
    let offset = 0
    for (const chunk of chunks) {
      body.set(chunk, offset)
      offset += chunk.length
    }
    headers['Content-Type'] = contentType
    headers['Idempotency-Key'] = key
  }
  try {
    const response = await $fetch.raw<ArrayBuffer>(config.url + path, {
      method: method as 'GET' | 'POST',
      headers,
      body,
      query: getQuery(event),
      responseType: 'arrayBuffer',
      timeout: 60000,
      retry: 0,
      ignoreResponseError: true,
    })
    setResponseStatus(event, response.status)
    setHeader(event, 'cache-control', 'private, no-store')
    setHeader(event, 'x-content-type-options', 'nosniff')
    for (const name of ['content-type', 'x-request-id']) {
      const value = response.headers.get(name)
      if (value) setHeader(event, name, value)
    }
    if (method === 'GET' && response.ok)
      setHeader(
        event,
        'content-disposition',
        response.headers.get('content-disposition') || 'attachment',
      )
    return new Uint8Array(response._data || new ArrayBuffer(0))
  } catch {
    setResponseStatus(event, 502)
    return {
      error: {
        code: 'BACKEND_UNAVAILABLE',
        message:
          method === 'POST'
            ? '未取得上传结果，请保留原文件并核实本次提交。'
            : '暂时无法下载原件，请稍后重试。',
        retryable: true,
      },
    }
  }
}
