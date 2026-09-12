import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

// Actual Vue components, fully intercepted transport; never forward business writes.
async function setup(page: Page) {
  const f = JSON.parse(
    readFileSync(new URL('./fixtures/overview-pending.json', import.meta.url), 'utf8'),
  )
  f.missions.items = []
  const store = 'overview-fixture-a'
  const item = (id: string) => ({
    id,
    store_id: store,
    principal_id: 'test-owner',
    title: id === 'work-a' ? '活动备货咨询' : '另一项查询',
    status: 'RESULT_READY',
    version: 1,
    summary: '已有结果',
    next_step: '',
    question: null,
    result: {
      kind: 'answer',
      title: '已有分析',
      content: '这是已保存的结果',
      columns: [],
      rows: [],
    },
    mission_id: null,
    mission: null,
    mission_request: null,
    demonstration: false,
    processor_available: true,
    processing_expires_at: null,
    created_at: '2026-09-09T03:00:00Z',
    updated_at: '2026-09-09T03:00:00Z',
  })
  const a: any = item('work-a'),
    b: any = item('work-b')
  a.mission_request = {
    store_id: store,
    sku_id: 'sku_001',
    objective: '核对后开始跟进',
    policy: {
      cash_floor_minor: 50000,
      candidate_quantities: [0, 20, 40, 80],
      supplier_id: 'supplier_001',
    },
    check_interval_seconds: 30,
  }
  const c = {
    items: [a, b],
    lists: 0,
    listStatus: 200,
    loseMessage: false,
    writes: [] as { path: string; key: string | undefined; body: any }[],
    messages: [] as any[],
  }
  await page.route('**/api/**', async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname.replace('/api/backend/api/v1/', '')
    if (url.pathname === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: 'test-owner',
          roles: ['admin'],
          agentEnabled: false,
          devTools: false,
          planRevision: true,
          workIntake: true,
        },
      })
    if (req.method() !== 'GET') {
      c.writes.push({ path, key: req.headers()['idempotency-key'], body: req.postDataJSON() })
      if (path === 'work-items/work-a/messages') {
        if (c.loseMessage) return route.abort('connectionreset')
        a.version++
        a.status = 'RECEIVED'
        a.mission_request = null
        c.messages.push({
          id: 'message-1',
          item_id: a.id,
          role: 'user',
          content: req.postDataJSON().content,
          created_at: a.created_at,
          result: null,
          demonstration: false,
        })
        return route.fulfill({ json: { item: a, messages: c.messages } })
      }
      return route.fulfill({
        status: 409,
        json: { error: { code: 'TEST_BLOCKED_WRITE', message: path } },
      })
    }
    if (path === 'stores')
      return route.fulfill({
        json: {
          items: [
            {
              store_id: store,
              currency: 'CNY',
              source_type: 'simulation',
              simulation_time: f.dashboard.state.simulation_time,
            },
          ],
          next_cursor: null,
          active_store: { store_id: store },
        },
      })
    if (path === 'work-items') {
      c.lists++
      if (c.listStatus !== 200)
        return route.fulfill({
          status: c.listStatus,
          json: {
            error: {
              code: c.listStatus === 401 ? 'UNAUTHENTICATED' : 'DEPENDENCY_UNAVAILABLE',
              message: '事项读取暂不可用',
            },
          },
        })
      return route.fulfill({
        json: { items: c.items, next_cursor: null, processor_available: true },
      })
    }
    if (path.startsWith('work-items/')) {
      const found = c.items.find((i) => i.id === path.split('/')[1])
      return found
        ? route.fulfill({ json: { item: found, messages: c.messages } })
        : route.fulfill({
            status: 404,
            json: { error: { code: 'RESOURCE_NOT_FOUND', message: 'missing' } },
          })
    }
    if (f[path]) return route.fulfill({ json: f[path] })
    return route.fulfill({
      status: 404,
      json: { error: { code: 'TEST_MISSING_READ', message: path } },
    })
  })
  await page.goto('/?store=' + store)
  await expect(page.locator('.work-card')).toHaveCount(2)
  return c
}

test('撤权停止事项重试；刷新身份后重新验证，不无限请求', async ({ page }) => {
  const c = await setup(page)
  await page.locator('[data-work-id="work-a"]').getByRole('button').click()
  await expect(page.locator('.work-detail')).toBeVisible()
  c.listStatus = 401
  await expect(
    page.getByText('当前身份的事项访问已失效，请重新连接。', { exact: true }),
  ).toBeVisible({ timeout: 10000 })
  const count = c.lists
  await page.waitForTimeout(3000)
  expect(c.lists).toBe(count)
  c.listStatus = 200
  await page.reload()
  await expect(page.locator('.work-detail')).toHaveAttribute('data-work-id', 'work-a')
  await expect(
    page.getByText('当前身份的事项访问已失效，请重新连接。', { exact: true }),
  ).toHaveCount(0)
})

test('消息结果未知时不能另建跟进覆盖原请求；重试沿用原键', async ({ page }) => {
  const c = await setup(page)
  await page.locator('[data-work-id="work-a"]').getByRole('button').click()
  await expect(page.getByRole('button', { name: '按这些条件开始跟进' })).toBeEnabled()
  c.loseMessage = true
  await page.getByLabel('继续说说你的要求').fill('先不要开始，我补充一个条件')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '查询并重试原提交' })).toBeVisible()
  await expect(page.getByRole('button', { name: '按这些条件开始跟进' })).toBeDisabled()
  c.loseMessage = false
  await page.getByRole('button', { name: '查询并重试原提交' }).click()
  await expect(page.getByRole('log', { name: '这件事的对话' })).toContainText('先不要开始')
  expect(c.writes).toHaveLength(2)
  expect(c.writes[0].key).toBe(c.writes[1].key)
  expect(c.writes.every((w) => w.path.endsWith('/messages'))).toBe(true)
})

test('失效的事项链接只影响该事项，其余卡片仍可打开', async ({ page }) => {
  const c = await setup(page)
  await page.goto('/?view=work&item=missing&store=overview-fixture-a')
  await expect(
    page.getByText('无法读取这件事，请返回今日选择可见事项。', { exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: '今日', exact: true }).first().click()
  await expect(page.locator('.work-card')).toHaveCount(2)
  await page.locator('[data-work-id="work-b"]').getByRole('button').click()
  await expect(page.locator('.work-detail')).toHaveAttribute('data-work-id', 'work-b')
  expect(c.writes).toEqual([])
})

test('事项列表连接恢复后清除旧错误，其他事项仍保留', async ({ page }) => {
  const c = await setup(page)
  c.listStatus = 503
  await expect(page.getByText('事项读取暂不可用', { exact: true })).toBeVisible({ timeout: 10000 })
  c.listStatus = 200
  await expect(page.getByText('事项读取暂不可用', { exact: true })).toHaveCount(0, {
    timeout: 10000,
  })
  await expect(page.locator('.work-card')).toHaveCount(2)
})
