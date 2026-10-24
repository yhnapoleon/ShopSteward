import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
const business = JSON.parse(
  readFileSync(new URL('./fixtures/overview.json', import.meta.url), 'utf8'),
)
const source = Buffer.from('# 供应商条款\n整箱12件，原件留存。\n')
const uploadFile = { name: '供货条款.md', mimeType: 'text/markdown', buffer: source }
const document = (id = 'doc-1', extra = {}) => ({
  id,
  title: '九月供货与到货约定',
  category: 'supplier_terms',
  visibility: 'store',
  sku_ids: [],
  supplier_ids: [],
  store_id: 'overview-fixture-a',
  owner_principal_id: 'operator',
  metadata_version: 1,
  status: 'active',
  latest_version_id: `${id}-v1`,
  ingestion_status: 'UPLOADED',
  indexing_status: 'NOT_INDEXED',
  created_at: '2026-09-08T02:00:00Z',
  updated_at: '2026-09-08T02:00:00Z',
  ...extra,
})
const version = (doc: ReturnType<typeof document>, no = 1) => ({
  id: `${doc.id}-v${no}`,
  document_id: doc.id,
  version_no: no,
  original_name: '供货条款.md',
  mime_type: 'text/markdown',
  size_bytes: source.length,
  content_sha256: 'a'.repeat(64),
  created_by: 'operator',
  created_at: '2026-09-08T02:00:00Z',
  valid_from: null,
  valid_until: null,
  ingestion_status: 'UPLOADED',
  indexing_status: 'NOT_INDEXED',
})
// All browser API traffic is controlled; these tests never forward writes or call a model.
async function setup(page: Page, count = 1) {
  const c = {
    docs: Array.from({ length: count }, (_, i) => document(`doc-${i + 1}`)),
    roles: ['operator'],
    principal: 'operator',
    active: 'overview-fixture-a',
    lost: false,
    conflict: false,
    denied: false,
    delay: 0,
    calls: [] as string[],
    writes: [] as string[],
    keys: [] as string[],
    receipts: new Map<string, any>(),
    versions: new Map<string, any[]>(),
  }
  for (const d of c.docs) c.versions.set(d.id, [version(d)])
  await page.route('**/api/**', async (route) => {
    const req = route.request(),
      url = new URL(req.url())
    const path = url.pathname.replace('/api/backend', '')
    c.calls.push(path)
    if (path === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: c.principal,
          roles: c.roles,
          agentEnabled: false,
          devTools: false,
          planRevision: true,
        },
      })
    if (path.startsWith('/api/v1/documents/') || /\/stores\/[^/]+\/documents$/.test(path)) {
      const id = path.split('/')[4]
      const d = c.docs.find((x) => x.id === id)
      const fail = (status: number, code: string) =>
        route.fulfill({ status, json: { error: { code } } })
      if (req.method() !== 'GET') {
        c.writes.push(path)
        const key = req.headers()['idempotency-key'] || ''
        c.keys.push(key)
        if (c.receipts.has(key)) return route.fulfill({ status: 201, json: c.receipts.get(key) })
        if (c.conflict) {
          c.conflict = false
          if (d) d.metadata_version++
          return fail(409, 'METADATA_VERSION_CONFLICT')
        }
        const text = req.postData() || ''
        const metadata = text.includes('name="metadata"')
          ? JSON.parse(text.match(/name="metadata"\r\n\r\n([\s\S]*?)\r\n--/)![1])
          : JSON.parse(text)
        let result = d
        if (path.includes('/stores/')) {
          result = document(`doc-${c.docs.length + 1}`, metadata)
          c.docs.unshift(result)
          c.versions.set(result.id, [version(result)])
        } else if (path.endsWith('/versions')) {
          const previous = c.versions.get(id) || []
          const next = version(d!, previous.length + 1)
          c.versions.set(id, [next, ...previous])
          d!.latest_version_id = next.id
          d!.metadata_version++
        } else if (path.endsWith('/control')) {
          d!.status = metadata.operation === 'archive' ? 'archived' : 'active'
          d!.metadata_version++
        } else {
          Object.assign(d!, metadata)
          d!.metadata_version++
        }
        c.receipts.set(key, structuredClone(result))
        if (c.lost) {
          c.lost = false
          return fail(502, 'BACKEND_UNAVAILABLE')
        }
        return route.fulfill({ status: 201, json: result })
      }
      if (path.includes('/stores/')) {
        const items = c.docs.filter(
          (d) =>
            d.store_id === c.active &&
            d.status === (url.searchParams.get('status') || 'active') &&
            (!url.searchParams.get('q') || d.title.includes(url.searchParams.get('q')!)) &&
            (!url.searchParams.get('category') || d.category === url.searchParams.get('category')),
        )
        const offset = Number(url.searchParams.get('cursor') || 0)
        return route.fulfill({
          json: {
            items: items.slice(offset, offset + 20),
            next_cursor: offset + 20 < items.length ? String(offset + 20) : null,
          },
        })
      }
      if (!d || c.denied) return fail(404, 'RESOURCE_NOT_FOUND')
      if (path.endsWith('/content'))
        return route.fulfill({
          body: source,
          headers: {
            'content-type': 'text/markdown',
            'content-disposition': "attachment; filename*=UTF-8''%E4%BE%9B%E8%B4%A7.md",
          },
        })
      if (path.endsWith('/versions')) {
        const items = c.versions.get(id) || [],
          offset = Number(url.searchParams.get('cursor') || 0)
        if (c.delay) await new Promise((r) => setTimeout(r, c.delay))
        return route.fulfill({
          json: {
            items: items.slice(offset, offset + 20),
            next_cursor: offset + 20 < items.length ? String(offset + 20) : null,
          },
        })
      }
      return route.fulfill({ json: d })
    }
    if (req.method() !== 'GET') throw Error('Unexpected business write: ' + path)
    if (path === '/api/v1/stores')
      return route.fulfill({
        json: {
          items: [{ store_id: c.active, currency: 'CNY', source_type: 'simulation' }],
          next_cursor: null,
          active_store: { store_id: c.active, currency: 'CNY', source_type: 'simulation' },
        },
      })
    const key = path.replace('/api/v1/', '')
    if (key.startsWith('plans/')) return route.fulfill({ json: business.plan })
    if (key.endsWith('/timeline')) return route.fulfill({ json: business.timeline })
    if (business[key]) return route.fulfill({ json: business[key] })
    return route.fulfill({ json: { items: [], next_cursor: null } })
  })
  return c
}
async function open(page: Page) {
  await page.goto('/?view=documents')
  await expect(page.getByRole('heading', { name: '把依据，留在手边。' })).toBeVisible()
  await expect(page.locator('.dc-library')).not.toHaveAttribute('aria-busy', 'true')
}
async function choose(page: Page) {
  await page.locator('.dc-document').first().click()
  await expect(page.getByRole('button', { name: /下载原件 v1/ })).toBeVisible()
}

test('资料可从既有入口进入；上传、版本、信息编辑、归档恢复和下载完整闭环', async ({ page }) => {
  const c = await setup(page, 0)
  await page.goto('/')
  await page.getByRole('button', { name: /文档中心 管理原件/ }).click()
  await expect(page.getByText('从第一份资料开始')).toBeVisible()
  await page.getByRole('button', { name: '上传资料', exact: true }).click()
  const modal = page.getByRole('dialog', { name: '上传资料', exact: true })
  await modal.getByLabel('选择原件').setInputFiles(uploadFile)
  await modal.getByRole('combobox', { name: '分类', exact: true }).selectOption('supplier_terms')
  await modal.getByRole('button', { name: '保存原件' }).click()
  await expect(modal).not.toBeVisible()
  await expect(page.locator('.dc-document')).toHaveCount(1)
  await expect(page.locator('.dc-detail-title')).toHaveText('供货条款')
  await page.getByRole('button', { name: '新版本', exact: true }).click()
  const append = page.getByRole('dialog', { name: '上传新版本' })
  await append.getByLabel('选择原件').setInputFiles(uploadFile)
  await append.getByRole('button', { name: '保存原件' }).click()
  await expect(page.locator('.dc-version')).toHaveCount(2)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: /下载原件 v2/ }).click()
  const saved = await download
  expect(saved.suggestedFilename()).toBe(uploadFile.name)
  expect(readFileSync((await saved.path())!)).toEqual(source)
  await page.getByRole('button', { name: '编辑信息' }).click()
  await page.getByRole('dialog').getByLabel('资料标题').fill('已更新的供货约定')
  await page.getByRole('button', { name: '保存信息' }).click()
  await expect(page.locator('.dc-detail-title')).toHaveText('已更新的供货约定')
  await page.getByRole('button', { name: '归档', exact: true }).click()
  await page.getByRole('button', { name: '确认归档' }).click()
  await expect(page.getByText('已收进归档')).toBeVisible()
  await expect(page.getByRole('button', { name: /下载原件 v/ })).toHaveCount(0)
  await page.getByRole('button', { name: '恢复资料', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: '恢复资料', exact: true }).click()
  await expect(page.locator('.dc-version')).toHaveCount(2)
  expect(c.writes).toHaveLength(5)
})

test('丢失上传响应后刷新，核对原文件并沿用同一幂等键，不重复建档', async ({ page }) => {
  const c = await setup(page, 0)
  c.lost = true
  await open(page)
  await page.getByRole('button', { name: '上传资料', exact: true }).click()
  await page.getByLabel('选择原件').setInputFiles(uploadFile)
  await page.getByRole('button', { name: '保存原件' }).click()
  await expect(page.getByRole('button', { name: '重试原提交' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '还有一笔资料提交待核实' })).toBeVisible()
  const recovery = page.getByRole('region', { name: '待核实的资料提交' })
  await recovery
    .locator('input[type=file]')
    .setInputFiles({ ...uploadFile, buffer: Buffer.from('different') })
  await recovery.getByRole('button', { name: '核实原提交' }).click()
  await expect(recovery.getByRole('alert')).toContainText('文件与原提交不一致')
  expect(c.writes).toHaveLength(1)
  await recovery.locator('input[type=file]').setInputFiles(uploadFile)
  await recovery.getByRole('button', { name: '核实原提交' }).click()
  await expect(recovery).not.toBeVisible()
  expect(c.docs).toHaveLength(1)
  expect(c.keys).toHaveLength(2)
  expect(c.keys[0]).toBe(c.keys[1])
})

test('版本冲突不会静默覆盖；载入最新资料后才能重新保存', async ({ page }) => {
  const c = await setup(page)
  await open(page)
  await choose(page)
  await page.getByRole('button', { name: '编辑信息' }).click()
  await page.getByRole('dialog').getByLabel('资料标题').fill('我的修订')
  c.conflict = true
  await page.getByRole('button', { name: '保存信息' }).click()
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('资料已被其他操作更新')
  expect(c.docs[0].title).toBe('九月供货与到货约定')
  await page.getByRole('button', { name: '载入最新资料' }).click()
  await expect(page.getByRole('dialog').getByLabel('资料标题')).toHaveValue('九月供货与到货约定')
  await page.getByRole('dialog').getByLabel('资料标题').fill('重新核对的修订')
  await page.getByRole('button', { name: '保存信息' }).click()
  await expect(page.locator('.dc-detail-title')).toHaveText('重新核对的修订')
})

test('只读身份与其他成员私有资料不显示写入或原件入口', async ({ page }) => {
  const c = await setup(page)
  c.roles = ['viewer']
  c.principal = 'viewer'
  await open(page)
  await choose(page)
  await expect(page.getByRole('button', { name: '上传资料', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '编辑信息' })).toHaveCount(0)
  c.roles = ['admin']
  c.principal = 'admin'
  c.docs[0].visibility = 'private'
  c.calls = []
  await page.reload()
  await page.locator('.dc-document').first().click()
  await expect(page.getByText('仅可查看资料信息')).toBeVisible()
  await expect(page.getByRole('button', { name: /下载原件 v/ })).toHaveCount(0)
  expect(c.calls.filter((x) => x.endsWith('/versions'))).toHaveLength(0)
})

test('标题筛选、资料分页和版本分页保留完整记录', async ({ page }) => {
  const c = await setup(page, 25)
  c.docs[0].title = '唯一活动资料'
  c.versions.set(
    c.docs[0].id,
    Array.from({ length: 23 }, (_, i) => version(c.docs[0], 23 - i)),
  )
  await open(page)
  await expect(page.locator('.dc-document')).toHaveCount(20)
  await page.getByRole('button', { name: '加载更多资料' }).click()
  await expect(page.locator('.dc-document')).toHaveCount(25)
  await page.getByLabel('搜索标题').fill('唯一')
  await page.getByRole('button', { name: '查找', exact: true }).click()
  await expect(page.locator('.dc-document')).toHaveCount(1)
  await page.locator('.dc-document').click()
  await expect(page.locator('.dc-version')).toHaveCount(20)
  await page.getByRole('button', { name: '加载更早版本' }).click()
  await expect(page.locator('.dc-version')).toHaveCount(23)
})

test('切换场景时迟到版本响应不能污染新店铺', async ({ page }) => {
  const c = await setup(page)
  c.delay = 4000
  await open(page)
  await page.locator('.dc-document').click()
  c.active = 'overview-fixture-b'
  await expect(page.locator('.dc-document')).toHaveCount(0)
  await page.waitForTimeout(4300)
  await expect(page.locator('.dc-version')).toHaveCount(0)
  await expect(page.locator('.dc-detail-title')).toHaveCount(0)
})

for (const recovering of [false, true]) {
  test(`${recovering ? '重试' : '首次'}上传校验期间切换场景，不再发起旧页面的写入`, async ({
    page,
  }) => {
    const c = await setup(page, recovering ? 0 : 1)
    if (recovering) {
      c.lost = true
      await open(page)
      await page.getByRole('button', { name: '上传资料', exact: true }).click()
      await page.getByLabel('选择原件').setInputFiles(uploadFile)
      await page.getByRole('button', { name: '保存原件' }).click()
      await expect(page.getByRole('button', { name: '重试原提交' })).toBeVisible()
    }
    await page.addInitScript(() => {
      const digest = crypto.subtle.digest.bind(crypto.subtle)
      let first = true
      crypto.subtle.digest = async (algorithm, data) => {
        if (first) {
          first = false
          await new Promise((resolve) => setTimeout(resolve, 5000))
        }
        return digest(algorithm, data)
      }
    })
    if (recovering) await page.reload()
    else await open(page)
    const baseline = c.writes.length
    if (recovering) {
      const recovery = page.getByRole('region', { name: '待核实的资料提交' })
      await recovery.locator('input[type=file]').setInputFiles(uploadFile)
      await recovery.getByRole('button', { name: '核实原提交' }).click()
    } else {
      await page.getByRole('button', { name: '上传资料', exact: true }).click()
      await page.getByLabel('选择原件').setInputFiles(uploadFile)
      await page.getByRole('button', { name: '保存原件' }).click()
    }
    c.active = 'overview-fixture-b'
    await expect(page.locator('.dc-document')).toHaveCount(0)
    await page.waitForTimeout(5500)
    expect(c.writes).toHaveLength(baseline)
    await expect(page.getByRole('region', { name: '待核实的资料提交' })).toHaveCount(0)
  })
}

test('无效文件在提交前阻止；手机布局、键盘弹层与焦点可用', async ({ page }) => {
  const c = await setup(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await open(page)
  await page.screenshot({ path: '../var/documents-e2e/mobile-list.png', fullPage: true })
  const button = page.getByRole('button', { name: '上传资料', exact: true })
  await button.focus()
  await page.keyboard.press('Enter')
  const modal = page.getByRole('dialog', { name: '上传资料', exact: true })
  await modal
    .getByLabel('选择原件')
    .setInputFiles({ name: 'bad.exe', mimeType: 'application/octet-stream', buffer: source })
  await modal.getByRole('button', { name: '保存原件' }).click()
  await expect(modal.getByRole('alert')).toContainText('支持PDF')
  expect(c.writes).toHaveLength(0)
  await modal
    .getByLabel('选择原件')
    .setInputFiles({ ...uploadFile, buffer: Buffer.alloc(20 * 1024 * 1024 + 1, 65) })
  await modal.getByRole('button', { name: '保存原件' }).click()
  await expect(modal.getByRole('alert')).toContainText('20 MiB')
  expect(c.writes).toHaveLength(0)
  await page.screenshot({ path: '../var/documents-e2e/mobile-upload.png', fullPage: true })
  await page.keyboard.press('Escape')
  await expect(button).toBeFocused()
  await choose(page)
  await page.screenshot({ path: '../var/documents-e2e/mobile-detail.png', fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('桌面长标题与可追溯详情，下载权限失效显示准确失败', async ({ page }) => {
  const c = await setup(page, 3)
  c.docs[1].title = '活动筹备与供货安排 · 包装、交付窗口和异常处理说明'
  c.docs[2].title = '经营复盘：保留原始记录，供下一次活动核对'
  await open(page)
  await choose(page)
  await page.screenshot({ path: '../var/documents-e2e/desktop.png', fullPage: true })
  await page.getByRole('button', { name: '新版本', exact: true }).click()
  await page.screenshot({ path: '../var/documents-e2e/desktop-upload.png', fullPage: true })
  await page.keyboard.press('Escape')
  c.denied = true
  await page.getByRole('button', { name: /下载原件 v1/ }).click()
  await expect(page.locator('.dc-detail').getByRole('alert')).toContainText('已无权访问')
})
