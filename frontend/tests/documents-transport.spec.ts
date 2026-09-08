import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash, randomUUID } from 'node:crypto'

// Requires the isolated API in support/documents_backend.py and a frontend pointed
// at port 8018. Never enable against the normal development API.
test.skip(process.env.DOCUMENTS_REAL !== 'true', 'Explicit isolated K1 HTTP environment required')
const credential = (role: string) => `mission-test-${role}-credential-0000000001`
const prefix = '/api/backend/api/v1'

test('真实代理与PG：multipart、幂等、下载字节和响应头、版本冲突、权限与归档', async ({
  playwright,
  baseURL,
}) => {
  const { store_id } = JSON.parse(
    readFileSync(new URL('../../var/documents-http/context.json', import.meta.url), 'utf8'),
  )
  const owner = await playwright.request.newContext({ baseURL })
  const viewer = await playwright.request.newContext({ baseURL })
  const admin = await playwright.request.newContext({ baseURL })
  for (const [client, role] of [
    [owner, 'operator'],
    [viewer, 'viewer'],
    [admin, 'admin'],
  ] as const) {
    expect((await client.post('/api/session', { data: { token: credential(role) } })).ok()).toBe(
      true,
    )
  }
  const before = await (await owner.get(`${prefix}/dashboard?store_id=${store_id}`)).json()
  const bytes = Buffer.from('\ufeff# 合成供货原件\r\n' + '包装12件，保留原始字节。\n'.repeat(12000))
  expect(bytes.length).toBeGreaterThan(256000)
  const key = randomUUID()
  const multipart = {
    metadata: JSON.stringify({ title: '真实HTTP文档验收', category: 'supplier_terms' }),
    file: { name: '合成供货条款.md', mimeType: 'text/markdown', buffer: bytes },
  }
  const create = () =>
    owner.post(`${prefix}/stores/${store_id}/documents`, {
      headers: { 'Idempotency-Key': key },
      multipart,
    })
  const first = await create()
  expect(first.status(), await first.text()).toBe(201)
  const doc = await first.json()
  expect((await (await create()).json()).id).toBe(doc.id)
  const path = `${prefix}/documents/${doc.id}`
  const versions = await (await owner.get(path + '/versions')).json()
  expect(versions.items).toHaveLength(1)
  expect(versions.items[0].content_sha256).toBe(createHash('sha256').update(bytes).digest('hex'))
  const originalPath = `${path}/versions/${versions.items[0].id}/content`
  const download = await owner.get(originalPath)
  expect(await download.body()).toEqual(bytes)
  expect(download.headers()['content-type']).toContain('text/markdown')
  expect(download.headers()['content-disposition']).toMatch(/^attachment;/)
  expect(download.headers()['content-disposition']).toContain('filename*=')
  expect(download.headers()['x-content-type-options']).toBe('nosniff')
  expect(download.headers()['cache-control']).toContain('no-store')
  expect(
    (
      await viewer.post(`${prefix}/stores/${store_id}/documents`, {
        headers: { 'Idempotency-Key': randomUUID() },
        multipart,
      })
    ).status(),
  ).toBe(403)
  expect(
    (
      await owner.post(`${prefix}/stores/${store_id}/documents`, {
        headers: { 'Idempotency-Key': randomUUID(), Origin: 'https://untrusted.example' },
        multipart,
      })
    ).status(),
  ).toBe(403)
  expect(
    (
      await owner.post(`${prefix}/missions`, {
        headers: { 'Idempotency-Key': randomUUID() },
        multipart,
      })
    ).status(),
  ).toBe(415)
  expect((await owner.post('/api/backend/internal/not-public', { multipart })).status()).toBe(404)
  const privateResult = await owner.patch(path, {
    headers: { 'Idempotency-Key': randomUUID() },
    data: { expected_metadata_version: 1, visibility: 'private' },
  })
  expect(privateResult.status()).toBe(200)
  expect((await viewer.get(originalPath)).status()).toBe(404)
  expect((await admin.get(path)).status()).toBe(200)
  expect((await admin.get(originalPath)).status()).toBe(404)
  expect(
    (
      await owner.patch(path, {
        headers: { 'Idempotency-Key': randomUUID() },
        data: { expected_metadata_version: 1, title: '过期修改' },
      })
    ).status(),
  ).toBe(409)
  const append = await owner.post(path + '/versions', {
    headers: { 'Idempotency-Key': randomUUID() },
    multipart: {
      metadata: JSON.stringify({ expected_metadata_version: 2 }),
      file: { ...multipart.file, buffer: Buffer.from('second version') },
    },
  })
  expect(append.status(), await append.text()).toBe(201)
  expect((await (await owner.get(path + '/versions')).json()).items).toHaveLength(2)
  for (const [operation, revision] of [
    ['archive', 3],
    ['restore', 4],
  ] as const) {
    const response = await owner.post(path + '/control', {
      headers: { 'Idempotency-Key': randomUUID() },
      data: { operation, expected_metadata_version: revision },
    })
    expect(response.status(), await response.text()).toBe(200)
    expect((await owner.get(originalPath)).status()).toBe(operation === 'archive' ? 404 : 200)
  }
  const oversized = await owner.post(`${prefix}/stores/${store_id}/documents`, {
    headers: { 'Idempotency-Key': randomUUID() },
    multipart: {
      ...multipart,
      file: { ...multipart.file, buffer: Buffer.alloc(20 * 1024 * 1024 + 128 * 1024 + 1, 65) },
    },
  })
  expect(oversized.status()).toBe(413)
  const after = await (await owner.get(`${prefix}/dashboard?store_id=${store_id}`)).json()
  expect(after.state).toEqual(before.state)
  await owner.dispose()
  await viewer.dispose()
  await admin.dispose()
})

test('真实浏览器上传、刷新取回与下载，经营账本不变', async ({ page }) => {
  expect(
    (await page.request.post('/api/session', { data: { token: credential('operator') } })).ok(),
  ).toBe(true)
  const title = '浏览器原件验收-' + randomUUID().slice(0, 8)
  const bytes = Buffer.from('# 浏览器原件\n确定性合成内容，用于文档中心验证。')
  await page.goto('/?view=documents')
  await page.getByRole('button', { name: '上传资料', exact: true }).click()
  const modal = page.getByRole('dialog', { name: '上传资料', exact: true })
  await modal
    .getByLabel('选择原件')
    .setInputFiles({ name: '浏览器原件.md', mimeType: 'text/markdown', buffer: bytes })
  await modal.getByLabel('资料标题').fill(title)
  await modal.getByRole('button', { name: '保存原件' }).click()
  await expect(modal).not.toBeVisible()
  await expect(page.locator('.dc-detail-title')).toHaveText(title)
  await page.reload()
  await page.getByLabel('搜索标题').fill(title)
  await page.getByRole('button', { name: '查找', exact: true }).click()
  await page.locator('.dc-document').filter({ hasText: title }).click()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: /下载原件 v1/ }).click()
  expect(readFileSync((await (await download).path())!)).toEqual(bytes)
  await page.screenshot({ path: '../var/documents-e2e/real-http.png', fullPage: true })
})
