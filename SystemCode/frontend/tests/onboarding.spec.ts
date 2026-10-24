import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

// Controlled browser transport: no store, model, ledger or purchase writes reach the backend.
async function setup(
  page: Page,
  options: { empty?: boolean; viewer?: boolean; english?: boolean } = {},
) {
  const fixture = JSON.parse(
    readFileSync(new URL('./fixtures/overview-pending.json', import.meta.url), 'utf8'),
  )
  const c = {
    active: options.empty ? '' : 'overview-fixture-a',
    principal: 'onboarding-test',
    writes: [] as { path: string; key?: string }[],
    failSave: false,
    items: [] as any[],
  }
  if (options.english)
    await page.addInitScript(() => localStorage.setItem('shopsteward.locale.v1', 'en'))
  await page.route('**/api/**', async (route) => {
    const req = route.request(),
      url = new URL(req.url())
    const path = url.pathname.replace('/api/backend/api/v1/', '')
    const store = url.searchParams.get('store_id') || c.active
    const f = JSON.parse(JSON.stringify(fixture).replaceAll('overview-fixture-a', store))
    f.missions.items = []
    f.actions.items = []
    f.inbounds.items = []
    if (url.pathname === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: c.principal,
          roles: [options.viewer ? 'viewer' : 'admin'],
          agentEnabled: false,
          devTools: false,
          quantitySimulation: true,
          workIntake: true,
        },
      })
    if (url.pathname === '/api/health') return route.fulfill({ json: { backend: 'ok' } })
    if (req.method() !== 'GET') {
      c.writes.push({ path, key: req.headers()['idempotency-key'] })
      if (path === `stores/${c.active}/simulations`) {
        if (c.failSave)
          return route.fulfill({
            status: 503,
            json: { error: { code: 'UNAVAILABLE', message: '试算暂不可用，请重试。' } },
          })
        const body = req.postDataJSON(),
          input = f.plan.input_snapshot
        const item = {
          id: 'guide-trial',
          store_id: c.active,
          principal_id: c.principal,
          title: '新手补货试算',
          status: 'RESULT_READY',
          version: 1,
          summary: '比较结果已保存',
          next_step: '',
          question: null,
          mission_id: null,
          mission: null,
          mission_request: null,
          demonstration: false,
          processor_available: false,
          business: null,
          processing_expires_at: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          result: {
            kind: 'analysis',
            title: '补货数量试算',
            content: '只比较，不采购。',
            assumptions: [],
            references: [],
            columns: [],
            rows: [],
            calculation: {
              schema_version: 'quantity-simulation-v1',
              rule_version: 'finite-candidates-v1',
              input_hash: 'test',
              request: body,
              candidates: f.plan.candidates,
              recommended_candidate_id: f.plan.recommended_candidate_id,
              valid_until: '2099-01-01T00:00:00Z',
              input: {
                ...input,
                state: f.dashboard.state,
                sku_id: body.sku_id,
                product_name: '示例商品',
                remaining_demand: 60,
                policy: { ...input.policy, cash_floor_minor: body.cash_floor_minor },
              },
            },
          },
        }
        c.items = [item]
        return route.fulfill({ json: { item, messages: [] } })
      }
      return route.fulfill({
        status: 409,
        json: { error: { code: 'BLOCKED_WRITE', message: path } },
      })
    }
    if (path === 'stores')
      return route.fulfill({
        json: {
          items: c.active
            ? ['overview-fixture-a', 'overview-fixture-b'].map((id) => ({
                store_id: id,
                currency: 'CNY',
                source_type: 'simulation',
                simulation_time: f.dashboard.state.simulation_time,
              }))
            : [],
          next_cursor: null,
          active_store: c.active ? { store_id: c.active } : null,
        },
      })
    if (path === 'work-items')
      return route.fulfill({
        json: {
          items: c.items.filter((i) => i.store_id === store),
          next_cursor: null,
          processor_available: false,
        },
      })
    if (path.startsWith('work-items/')) {
      const item = c.items.find((i) => i.id === path.split('/')[1] && i.store_id === c.active)
      return item
        ? route.fulfill({ json: { item, messages: [] } })
        : route.fulfill({
            status: 404,
            json: { error: { code: 'RESOURCE_NOT_FOUND', message: '不可读取' } },
          })
    }
    if (f[path]) return route.fulfill({ json: f[path] })
    return route.fulfill({ status: 404, json: { error: { code: 'UNAVAILABLE', message: path } } })
  })
  await page.goto('/')
  await expect(
    page.getByRole('button', {
      name: options.english ? 'Start the guide' : '开始体验',
      exact: true,
    }),
  ).toBeVisible()
  return c
}
const guide = (page: Page) => page.locator('.onboarding-coach')
async function reachTrial(page: Page) {
  await page.getByRole('button', { name: '开始体验', exact: true }).click()
  await guide(page).getByRole('button', { name: '店铺没问题，继续' }).click()
  await guide(page).getByRole('button', { name: '我找到了', exact: true }).click()
  await expect(guide(page)).toContainText('亲手做一次补货试算')
}

test('实际保存后才推进，能从记录找回结果，完成过程不采购', async ({ page }) => {
  const c = await setup(page)
  await reachTrial(page)
  expect(c.writes).toEqual([])
  await guide(page).getByRole('button', { name: '打开补货试算' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('新手指引第 4 步')
  await page.getByLabel('比较数量（件，以逗号分隔）').fill('0, 20, 40')
  c.failSave = true
  await dialog.getByRole('button', { name: '比较并保存结果', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('试算暂不可用')
  await expect(dialog.getByRole('button', { name: '查询并重试原试算' })).toBeVisible()
  c.failSave = false
  await dialog.getByRole('button', { name: '查询并重试原试算' }).click()
  await expect(guide(page)).toContainText('试算结果已经保存')
  expect(c.writes).toHaveLength(2)
  expect(c.writes[0].key).toBe(c.writes[1].key)
  await guide(page).getByRole('button', { name: '我明白了，去找回结果' }).click()
  await expect(page).toHaveURL(/view=journal/)
  await expect(guide(page).getByRole('button', { name: '完成指引', exact: true })).toBeDisabled()
  await page.locator('[data-work-id="guide-trial"]').getByRole('button').click()
  await expect(guide(page)).toContainText('已经重新打开这份试算')
  await guide(page).getByRole('button', { name: '完成指引', exact: true }).click()
  await expect(page.getByText('你已经认识了基本操作', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.locator('.onboarding-invite')).toHaveCount(0)
  await page.getByRole('button', { name: '设置', exact: true }).first().click()
  await page.getByRole('button', { name: '重新查看新手指引' }).click()
  await reachTrial(page)
  await guide(page).getByRole('button', { name: '查看已有试算并继续' }).click()
  await expect(guide(page)).toContainText('试算结果已经保存')
  expect(c.writes).toHaveLength(2)
  expect(c.writes.every((w) => w.path.endsWith('/simulations'))).toBe(true)
})

test('身份隔离与失效结果恢复，不把旧结果当成当前成功', async ({ page }) => {
  const c = await setup(page)
  await reachTrial(page)
  const stateKey = 'shopsteward.onboarding.v1:' + encodeURIComponent(c.principal)
  await page.evaluate(
    (key) =>
      localStorage.setItem(
        key,
        JSON.stringify({
          status: 'active',
          step: 4,
          storeId: 'overview-fixture-a',
          resultId: 'missing-result',
          resultOpened: false,
          simulationSkipped: false,
        }),
      ),
    stateKey,
  )
  await page.reload()
  await page.getByRole('button', { name: '继续指引', exact: true }).click()
  await expect(guide(page)).toContainText('之前的试算暂时无法读取')
  await expect(guide(page)).toContainText('亲手做一次补货试算')
  c.principal = 'another-user'
  await page.reload()
  await expect(page.getByRole('button', { name: '开始体验', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '继续指引', exact: true })).toHaveCount(0)
  expect(c.writes).toEqual([])
})

test('可以跳过，刷新不再弹出，并能从设置重新开始', async ({ page }) => {
  const c = await setup(page)
  await page.getByRole('button', { name: '稍后再说' }).click()
  await page.reload()
  await expect(page.getByRole('heading', { name: '今天的经营安排。' })).toBeVisible()
  await expect(page.locator('.onboarding-invite')).toHaveCount(0)
  await page.getByRole('button', { name: '设置', exact: true }).first().click()
  await page.getByRole('button', { name: '重新查看新手指引' }).click()
  await expect(page.getByRole('button', { name: '开始体验', exact: true })).toBeVisible()
  expect(c.writes).toEqual([])
})

test('刷新可恢复到原步骤，保存进度失败也不会阻塞使用', async ({ page }) => {
  const c = await setup(page)
  await reachTrial(page)
  await page.reload()
  await page.getByRole('button', { name: '继续指引', exact: true }).click()
  await expect(guide(page)).toContainText('亲手做一次补货试算')
  await page.evaluate(() => {
    const original = Storage.prototype.setItem
    Storage.prototype.setItem = function (key, value) {
      if (key.startsWith('shopsteward.onboarding.')) throw new Error('storage denied')
      original.call(this, key, value)
    }
  })
  await guide(page).getByRole('button', { name: '上一步' }).click()
  await expect(guide(page)).toContainText('浏览器暂时无法保存指引进度')
  await guide(page).getByRole('button', { name: '我找到了', exact: true }).click()
  await expect(guide(page)).toContainText('亲手做一次补货试算')
  expect(c.writes).toEqual([])
})

test('没有店铺时等待准备，不能把未读取的数据当成完成', async ({ page }) => {
  const c = await setup(page, { empty: true })
  await page.getByRole('button', { name: '开始体验', exact: true }).click()
  await expect(guide(page)).toContainText('等待店铺与经营数据就绪')
  await expect(guide(page).getByRole('button', { name: '店铺没问题，继续' })).toBeDisabled()
  await guide(page).getByRole('button', { name: '选择或准备店铺' }).click()
  await expect(page.getByRole('dialog').getByLabel('当前可访问的店铺')).toContainText('尚无场景')
  expect(c.writes).toEqual([])
})

test('只读身份可以跳过试算并了解流程，不声称保存或下单', async ({ page }) => {
  const c = await setup(page, { viewer: true })
  await reachTrial(page)
  await expect(guide(page).getByRole('button', { name: '打开补货试算' })).toHaveCount(0)
  await guide(page).getByRole('button', { name: '跳过试算，先了解后续操作' }).click()
  await expect(guide(page)).toContainText('本轮跳过了试算，尚未保存新的结果')
  await guide(page).getByRole('button', { name: '我明白了，去找回结果' }).click()
  await guide(page).getByRole('button', { name: '完成指引', exact: true }).click()
  expect(c.writes).toEqual([])
})

test('切换店铺后重新核对，不沿用旧店铺的进度或结果', async ({ page }) => {
  const c = await setup(page)
  await reachTrial(page)
  await guide(page).getByRole('button', { name: '暂停新手指引' }).click()
  await page.locator('[data-onboarding="store"]').first().click()
  c.active = 'overview-fixture-b'
  await page.getByRole('dialog').getByLabel('当前可访问的店铺').selectOption(c.active)
  await page.getByRole('button', { name: '继续指引', exact: true }).click()
  await expect(guide(page)).toContainText('先确认你在看哪家店铺')
  expect(c.writes).toEqual([])
})

test('英文手机界面可操作，无横向溢出，键盘可暂停指引', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const c = await setup(page, { english: true })
  await page.getByRole('button', { name: 'Start the guide', exact: true }).click()
  await expect(guide(page)).toContainText('Step 2 of 6')
  await expect(guide(page)).toContainText('Check which store you are viewing')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '../var/frontend-e2e/onboarding-mobile.png' })
  await guide(page).press('Escape')
  await expect(page.getByRole('button', { name: 'Continue guide', exact: true })).toBeVisible()
  expect(c.writes).toEqual([])
})
