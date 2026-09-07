import { backendSettings, sameOrigin } from '../utils/backend'
export default defineEventHandler(async (event) => {
  sameOrigin(event)
  const { token } = await readBody<{ token: string }>(event)
  if (typeof token !== 'string' || token.length > 4096 || token.length < 12)
    throw createError({ statusCode: 400, statusMessage: '请输入有效的后端用户凭证' })
  const config = backendSettings(event)
  try {
    await $fetch(config.url + '/api/v1/me', {
      headers: { Authorization: 'Bearer ' + token },
      timeout: 10000,
      retry: 0,
    })
  } catch {
    throw createError({ statusCode: 401, statusMessage: '无法验证后端身份，请检查凭证和服务' })
  }
  setCookie(event, 'shopsteward-session', token, {
    httpOnly: true,
    sameSite: 'strict',
    secure: getRequestURL(event).protocol === 'https:',
    path: '/',
    maxAge: 43200,
  })
  return { ok: true }
})
