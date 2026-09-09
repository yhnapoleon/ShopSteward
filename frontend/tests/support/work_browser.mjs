import { chromium, expect } from '@playwright/test'
import { writeFile } from 'node:fs/promises'
const base = process.env.WORK_FRONTEND,
  backend = process.env.WORK_BACKEND,
  store = process.env.WORK_STORE,
  output = process.env.WORK_OUTPUT
for (const url of [base, backend])
  if (new URL(url).hostname !== '127.0.0.1') throw Error('Loopback only')
const browser = await chromium.launch({ headless: true }),
  checks = []
const page = await browser.newPage({
  viewport: { width: 1440, height: 1100 },
  reducedMotion: 'reduce',
})
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
const service = { Authorization: 'Bearer ' + process.env.WORK_SERVICE }
async function read(id) {
  const r = await page.request.get(base + '/api/backend/api/v1/work-items/' + id)
  expect(r.ok()).toBe(true)
  return r.json()
}
async function lease(id) {
  const d = await read(id)
  const r = await page.request.post(backend + '/internal/v1/work-items/' + id + '/claim', {
    headers: { ...service, 'Idempotency-Key': crypto.randomUUID() },
    data: { expected_version: d.item.version },
  })
  expect(r.ok(), await r.text()).toBe(true)
  return r.json()
}
async function publish(id, l, changes) {
  const r = await page.request.post(backend + '/internal/v1/work-items/' + id + '/updates', {
    headers: { ...service, 'Idempotency-Key': crypto.randomUUID() },
    data: {
      expected_version: l.work.item.version,
      processing_token: l.processing_token,
      demonstration: true,
      ...changes,
    },
  })
  return r
}
async function screenshot(name) {
  await page.evaluate(() => scrollTo(0, 0))
  await page.screenshot({ path: output + '/' + name + '.jpg', type: 'jpeg', quality: 65 })
}
try {
  expect(
    (
      await page.request.post(base + '/api/session', { data: { token: process.env.WORK_AUTH } })
    ).ok(),
  ).toBe(true)
  expect((await page.request.get(backend + '/openapi.json')).status()).toBe(404)
  const identity = await (await page.request.get(base + '/api/session')).json()
  expect(identity.workIntake).toBe(true)
  expect(identity.planRevision).toBe(true)
  checks.push('normal identity capabilities work with OpenAPI documentation disabled')
  await page.goto(base + '/?store=' + store)
  await expect(page.getByRole('heading', { name: '今天想解决什么事？' })).toBeVisible({
    timeout: 20000,
  })
  await screenshot('empty')
  // Lose the response after the real API has committed. Refresh and replay the same key.
  let lost = false
  await page.route('**/api/backend/api/v1/work-items', async (route) => {
    if (route.request().method() === 'POST' && !lost) {
      lost = true
      await route.fetch()
      return route.abort('connectionreset')
    }
    return route.continue()
  })
  await page
    .getByLabel('把事情告诉我', { exact: true })
    .fill('下周活动，看看牛奶够不够，至少留500元')
  await page.getByRole('button', { name: '交给助手', exact: true }).click()
  await expect(page.getByRole('button', { name: '恢复原提交', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: '交给我一件事', exact: true })).toBeVisible()
  // The accepted card may already be listed, while the unknown submission remains recoverable.
  await page.getByRole('button', { name: '交给我一件事', exact: true }).click()
  await page.getByRole('button', { name: '恢复原提交', exact: true }).click()
  await expect(page.locator('.work-detail')).toBeVisible()
  const id = await page.locator('.work-detail').getAttribute('data-work-id')
  expect((await read(id)).messages.filter((m) => m.role === 'user')).toHaveLength(1)
  checks.push('real committed create + lost response + refresh replays once')
  const context = await page.request.get(backend + '/internal/v1/work-items/' + id + '/context', {
    headers: service,
  })
  expect(context.ok(), await context.text()).toBe(true)
  expect((await context.json()).catalog.products.length).toBeGreaterThan(0)
  let l = await lease(id)
  expect(
    (
      await publish(id, l, {
        status: 'WAITING_INPUT',
        question: '活动具体是哪几天？',
        summary: '已保留500元底线，仍需活动日期。',
        next_step: '请补充活动日期',
      })
    ).ok(),
  ).toBe(true)
  await expect(page.getByRole('heading', { name: '还需要你补充' })).toBeVisible({ timeout: 10000 })
  await screenshot('clarification')
  await page.reload()
  await expect(page.getByLabel('补充这件事需要的信息')).toBeVisible()
  await page.getByLabel('补充这件事需要的信息').fill('下周六和周日，先只分析')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect
    .poll(async () => (await read(id)).messages.filter((m) => m.role === 'user').length)
    .toBe(2)
  l = await lease(id)
  await page.getByLabel('继续说说你的要求').fill('补充一下：还要保留现有在途')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect
    .poll(async () => (await read(id)).messages.filter((m) => m.role === 'user').length)
    .toBe(3)
  expect(
    (
      await publish(id, l, {
        status: 'COMPLETED',
        result: { kind: 'answer', title: '过时结果', content: '不应显示' },
      })
    ).status(),
  ).toBe(409)
  l = await lease(id)
  expect(
    (
      await publish(id, l, {
        status: 'COMPLETED',
        title: '活动库存检查',
        summary: '分析结果已保存',
        result: {
          kind: 'forecast',
          title: '活动分析示例',
          content: '这是模拟接入结果。缺对应周期需求，尚不能断言够卖。',
          columns: ['条件', '说明'],
          rows: [
            ['现金底线', '500元'],
            ['周期', '用户补充的日期'],
          ],
          assumptions: ['预测并非实际销售'],
          references: [{ type: 'store', id: store, label: '当前店铺' }],
        },
      })
    ).ok(),
  ).toBe(true)
  await expect(
    page.getByRole('heading', { name: '活动分析示例', exact: true }).first(),
  ).toBeVisible({ timeout: 10000 })
  await screenshot('result-desktop')
  await page.setViewportSize({ width: 390, height: 844 })
  await screenshot('result-mobile')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  )
  await page.reload()
  await expect(
    page.getByRole('heading', { name: '活动分析示例', exact: true }).first(),
  ).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '保存结果', exact: true }).first().click()
  expect((await download).suggestedFilename()).toBe('事项结果.txt')
  checks.push(
    'clarification, steering, stale callback rejected, durable forecast + download, mobile',
  )
  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.getByRole('button', { name: '返回今日', exact: true }).click()
  await page.getByRole('button', { name: '经营记录', exact: true }).first().click()
  await expect(page.locator('.work-card[data-work-id="' + id + '"]')).toBeVisible()
  await page
    .locator('.work-card[data-work-id="' + id + '"]')
    .getByRole('button')
    .click()
  expect(await page.locator('.work-detail').getAttribute('data-work-id')).toBe(id)
  // Real existing mission: test fixture creates it; the adapter only associates the intake.
  const mr = await page.request.post(base + '/api/backend/api/v1/missions', {
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    data: {
      store_id: store,
      sku_id: 'sku_001',
      objective: '保留原备货安排',
      policy: {
        cash_floor_minor: 30000,
        candidate_quantities: [0, 20, 40, 80],
        supplier_id: 'supplier_001',
      },
      check_interval_seconds: 30,
    },
  })
  expect(mr.ok(), await mr.text()).toBe(true)
  const mission = await mr.json()
  await page.getByLabel('继续说说你的要求').fill('接回已有备货安排')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect.poll(async () => (await read(id)).item.status).toBe('RECEIVED')
  l = await lease(id)
  expect(
    (
      await publish(id, l, {
        status: 'RESULT_READY',
        link_mission_id: mission.id,
        summary: '已关联原工作',
        result: {
          kind: 'answer',
          title: '接回原安排',
          content: '原采购未改变，可继续核对业务进度。',
        },
      })
    ).ok(),
  ).toBe(true)
  await expect(page.locator('.task-workspace')).toBeVisible({ timeout: 10000 })
  await expect(page.getByRole('log', { name: '这件事的对话' })).toContainText('至少留500元')
  await screenshot('linked-mission')
  await page.reload()
  await expect(page.locator('.task-workspace')).toBeVisible()
  expect((await read(id)).item.mission_id).toBe(mission.id)
  const actions = await (
    await page.request.get(base + '/api/backend/api/v1/actions?store_id=' + store)
  ).json()
  expect(actions.items).toHaveLength(0)
  checks.push(
    'same item across history and mission association; original dialog retained; purchases zero',
  )
  expect(errors).toEqual([])
  await writeFile(
    output + '/results.json',
    JSON.stringify(
      { checks, errors, store, item: id, mission: mission.id, model_calls: 0, purchases: 0 },
      null,
      2,
    ),
  )
} catch (e) {
  await screenshot('failure')
  throw e
} finally {
  await browser.close()
}
