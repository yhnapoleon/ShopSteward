import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
const fixture = JSON.parse(
  readFileSync(new URL('./fixtures/overview.json', import.meta.url), 'utf8'),
)
const pendingFixture = JSON.parse(
  readFileSync(new URL('./fixtures/overview-pending.json', import.meta.url), 'utf8'),
)
import { cashHistory, salesRange } from '../app/utils/overview'

// Entire browser transport is controlled. No test in this file creates a store,
// changes the simulator, sends a model request, or forwards a purchase.
type Controls = {
  active: string
  failures: Set<string>
  delaySales: number
  detailDelay: number
  salesCount: number
  mixed: boolean
  partial: boolean
  noMission: boolean
  pendingDecision: boolean
  staleLedger: boolean
  calls: string[]
  writes: string[]
}
async function setup(page: Page) {
  const control: Controls = {
    active: 'overview-fixture-a',
    failures: new Set(),
    delaySales: 0,
    detailDelay: 0,
    salesCount: 1,
    mixed: false,
    partial: false,
    noMission: false,
    pendingDecision: false,
    staleLedger: false,
    calls: [],
    writes: [],
  }
  await page.route('**/api/**', async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname.replace('/api/backend/api/v1/', '')
    control.calls.push(path)
    if (req.method() !== 'GET') {
      control.writes.push(path)
      return route.fulfill({
        status: 409,
        json: {
          error: { code: 'TEST_WRITE_BLOCKED', message: 'No writes are forwarded by this test.' },
        },
      })
    }
    if (url.pathname === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: 'test-owner',
          roles: ['admin'],
          store_scope: 'ALL',
          agentEnabled: false,
          devTools: true,
          planRevision: true,
        },
      })
    const id = url.searchParams.get('store_id') || control.active
    const b = id.endsWith('-b')
    const f: any = JSON.parse(
      JSON.stringify(control.pendingDecision ? pendingFixture : fixture).replaceAll(
        'overview-fixture-a',
        id,
      ),
    )
    if (b) {
      Object.assign(f.dashboard.state, {
        cash_minor: 123400,
        available_cash_minor: 123400,
        receivables_minor: 0,
        state_version: 1,
      })
      Object.assign(f.dashboard.state.stocks[0], { on_hand: 37, in_transit: 0 })
      f.inbounds.items = []
      f.actions.items = []
      f.missions.items = []
      f.plan = null
      const initial = f['ledger-entries'].items.find((x: any) => x.effect_type === 'INIT')
      initial.opening_state = structuredClone(f.dashboard.state)
      initial.state_version = 1
      f['ledger-entries'].items = [initial]
    }
    // S5 for the visual fixture, using only supported fields and no backend writes.
    if (!b && !control.pendingDecision) {
      f.dashboard.state.simulation_time = f['ledger-entries'].items.find(
        (x: any) => x.effect_type === 'DEMAND_REVISED',
      ).simulation_time
      f['ledger-entries'].items = f['ledger-entries'].items.filter(
        (x: any) => !(x.effect_type === 'GOODS_RECEIVED' && x.changes?.on_hand_delta === 20),
      )
      Object.assign(f.dashboard.state.stocks[0], { on_hand: 50, in_transit: 20 })
      const second = f.inbounds.items.find((x: any) => x.ordered_quantity === 20)
      Object.assign(second, {
        received_quantity: control.partial ? 5 : 0,
        remaining_quantity: control.partial ? 15 : 20,
        arrival_status: control.partial ? 'PARTIALLY_RECEIVED' : 'NOT_RECEIVED',
        expected_arrival_at: control.partial ? null : second.expected_arrival_at,
        is_overdue: control.partial ? null : false,
      })
    }
    if (control.noMission) {
      f.missions.items = []
      f.plan = null
    }
    const ctx = structuredClone(f.sales.context)
    Object.assign(ctx, {
      store_id: id,
      state_version: f.dashboard.state.state_version,
      simulation_time: f.dashboard.state.simulation_time,
    })
    for (const resource of ['sales', 'inbounds', 'actions', 'ledger-entries'])
      f[resource].context = structuredClone(ctx)
    if (control.staleLedger) f['ledger-entries'].context.freshness.status = 'STALE'
    if (path === 'stores') {
      const store = (store_id: string) => ({
        store_id,
        currency: 'CNY',
        source_type: 'simulation',
        simulation_time: f.dashboard.state.simulation_time,
      })
      return route.fulfill({
        json: {
          items: [store('overview-fixture-a'), store('overview-fixture-b')],
          next_cursor: null,
          active_store: store(control.active),
        },
      })
    }
    if (control.failures.has(path))
      return route.fulfill({
        status: 503,
        json: { error: { code: 'READ_FAILED', message: '受控读取失败' } },
      })
    if (path === 'sales/summary' || path === 'sales') {
      const from = url.searchParams.get('from') || '2026-09-01T00:00:00Z',
        to = url.searchParams.get('to') || '2026-09-10T00:00:00Z'
      const source = f.sales.items[0]
      const records = b
        ? []
        : Array.from({ length: control.salesCount }, (_, i) => ({
            ...source,
            event_id: `sale-${i}`,
            sequence: i + 1,
            quantity: control.salesCount === 1 ? 10 : 1,
            sales_amount_minor: control.salesCount === 1 ? 20000 : 2000,
          }))
      const filtered = records.filter(
        (x) =>
          Date.parse(x.simulation_time) >= Date.parse(from) &&
          Date.parse(x.simulation_time) < Date.parse(to),
      )
      if (control.mixed) ctx.state_version += 1
      if (path === 'sales/summary') {
        const buckets = []
        for (let t = Date.parse(from); t < Date.parse(to); t += 86400000) {
          const matches = filtered.filter(
            (x) =>
              Date.parse(x.simulation_time) >= t && Date.parse(x.simulation_time) < t + 86400000,
          )
          buckets.push({
            from: new Date(t).toISOString(),
            to: new Date(Math.min(t + 86400000, Date.parse(to))).toISOString(),
            record_count: matches.length,
            recorded_quantity: matches.reduce((n, x) => n + x.quantity, 0),
            recorded_sales_amount_minor: matches.reduce((n, x) => n + x.sales_amount_minor, 0),
          })
        }
        const data = {
          context: ctx,
          from,
          to,
          time_basis: 'simulation_time',
          timezone: 'UTC',
          granularity: 'day',
          coverage: 'RECORDED_EVENTS_ONLY',
          record_count: filtered.length,
          recorded_quantity: filtered.reduce((n, x) => n + x.quantity, 0),
          recorded_sales_amount_minor: filtered.reduce((n, x) => n + x.sales_amount_minor, 0),
          buckets,
        }
        if (!b && control.delaySales) await new Promise((r) => setTimeout(r, control.delaySales))
        return route.fulfill({ json: data })
      }
      const offset = Number(url.searchParams.get('cursor') || 0),
        limit = Number(url.searchParams.get('limit') || 30)
      const data = {
        context: ctx,
        items: filtered.slice(offset, offset + limit),
        next_cursor: offset + limit < filtered.length ? String(offset + limit) : null,
      }
      if (control.detailDelay) await new Promise((r) => setTimeout(r, control.detailDelay))
      return route.fulfill({ json: data })
    }
    if (path.startsWith('plans/')) return route.fulfill({ json: f.plan })
    if (path.endsWith('/timeline')) return route.fulfill({ json: f.timeline })
    if (path.endsWith('/conversations'))
      return route.fulfill({ json: { items: [], next_cursor: null } })
    if (f[path]) return route.fulfill({ json: f[path] })
    return route.fulfill({
      status: 404,
      json: { error: { code: 'TEST_UNKNOWN_READ', message: path } },
    })
  })
  return control
}
async function openOverview(page: Page) {
  await page.goto('/?view=overview')
  await expect(page.getByTestId('overview-cash')).toHaveText('¥400')
  await expect(page.getByTestId('overview-sales-quantity')).toHaveText('10件')
  await expect(page.locator('.overview-chart--sales svg')).toBeVisible()
}

test('默认今日，次级入口与返回保留原工作区；概览不发写请求', async ({ page }) => {
  const c = await setup(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '今天的经营安排。' })).toBeVisible()
  await expect(page.getByTestId('business-overview')).toHaveCount(0)
  expect(c.calls).not.toContain('sales/summary')
  await page.locator('.rail .overview-entry').click()
  await expect(page.getByTestId('overview-cash')).toHaveText('¥400')
  await expect(page.getByTestId('overview-stock')).toHaveText('50')
  await page.getByRole('button', { name: '返回今日', exact: true }).click()
  await expect(page.getByRole('heading', { name: '今天的经营安排。' })).toBeVisible()
  await expect(page.getByLabel('追问这项备货任务', { exact: true })).toBeAttached()
  expect(c.writes).toEqual([])
})

test('UTC销售区间、金额切换与现金事件图；仅影响销售区间', async ({ page }) => {
  const c = await setup(page)
  await openOverview(page)
  await page
    .getByRole('group', { name: '销售图表指标' })
    .getByRole('button', { name: '金额' })
    .click()
  await expect(page.getByTestId('overview-sales-amount')).toHaveText('¥200')
  await page.getByLabel('销售时间范围').selectOption('30')
  await expect(page.locator('.overview-chart-footer')).toContainText('08/10 — 09/08')
  await expect(page.getByTestId('overview-cash')).toHaveText('¥400')
  await page.getByRole('button', { name: '查看现金变化明细' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('¥1,000')
  await expect(dialog).toContainText('¥600')
  await expect(dialog).toContainText('¥400')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('button', { name: '查看现金变化明细' })).toBeFocused()
  expect(c.writes).toEqual([])
})

test('销售总量不依赖明细第一页，明细可完整翻页', async ({ page }) => {
  const c = await setup(page)
  c.salesCount = 65
  await page.goto('/?view=overview')
  await expect(page.getByTestId('overview-sales-quantity')).toHaveText('65件')
  await page.getByRole('button', { name: '销售明细', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.locator('tbody tr')).toHaveCount(30)
  await dialog.getByRole('button', { name: '加载更多' }).click()
  await expect(dialog.locator('tbody tr')).toHaveCount(60)
  await dialog.getByRole('button', { name: '加载更多' }).click()
  await expect(dialog.locator('tbody tr')).toHaveCount(65)
  await expect(dialog.getByRole('button', { name: '加载更多' })).toHaveCount(0)
  expect(c.writes).toEqual([])
})

test('刷新失败保留原值并显式标记，区间切换不保留旧总量', async ({ page }) => {
  const c = await setup(page)
  await openOverview(page)
  c.failures.add('sales/summary')
  await page.getByRole('button', { name: '刷新经营概览' }).click()
  await expect(page.locator('.overview-sales')).toContainText('读取失败 · 保留上次数据')
  await expect(page.getByTestId('overview-sales-quantity')).toHaveText('10件')
  await page.getByLabel('销售时间范围').selectOption('30')
  await expect(page.getByTestId('overview-sales-quantity')).toHaveText('未取得')
  c.failures.clear()
  await page.getByRole('button', { name: '刷新经营概览' }).click()
  await expect(page.getByTestId('overview-sales-quantity')).toHaveText('10件')
})

test('不同快照、部分到货及未知ETA，不伪装成一致或已收完', async ({ page }) => {
  const c = await setup(page)
  c.mixed = true
  c.partial = true
  c.noMission = true
  await openOverview(page)
  await expect(page.locator('.overview-warning')).toContainText('读取时点不同')
  await expect(page.locator('.overview-inbounds')).toContainText('已收 5/20')
  await expect(page.locator('.overview-inbounds')).toContainText('到货时间未知')
  await expect(page.locator('.overview-floor')).toHaveCount(0)
})

test('新环境自动切换，旧场景迟到的销售响应不能污染新页面', async ({ page }) => {
  const c = await setup(page)
  c.delaySales = 5000
  await page.goto('/?view=overview')
  await expect(page.getByTestId('overview-cash')).toHaveText('¥400')
  c.active = 'overview-fixture-b'
  await expect(page.getByTestId('overview-cash')).toHaveText('¥1,234')
  await expect(page.getByTestId('overview-stock')).toHaveText('37')
  await expect(page.getByTestId('overview-sales-quantity')).toHaveText('0件')
  await page.waitForTimeout(3000)
  await expect(page.getByTestId('overview-cash')).toHaveText('¥1,234')
  await expect(page.getByTestId('overview-sales-quantity')).toHaveText('0件')
  expect(c.writes).toEqual([])
})

test('图表键盘、日期弹层和手机浏览均可操作，无页面溢出', async ({ page }) => {
  const c = await setup(page)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await openOverview(page)
  await page.locator('.overview-chart--sales').focus()
  await page.keyboard.press('End')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog')).toContainText('销售明细')
  await page.keyboard.press('Escape')
  await page.getByLabel('销售时间范围').selectOption('custom')
  await page.getByLabel('开始日期').fill('2026-09-08')
  await page.getByLabel('结束日期').fill('2026-09-08')
  await page.getByRole('button', { name: '应用区间' }).click()
  await expect(page.locator('.overview-chart-footer')).toContainText('09/08 — 09/08')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: '库存明细', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('剩余需求假设')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '返回今日', exact: true }).click()
  await page.locator('.fact-strip').getByRole('button', { name: '经营概览' }).click()
  await expect(page.getByTestId('overview-cash')).toHaveText('¥400')
  expect(errors).toEqual([])
  expect(c.writes).toEqual([])
})

test('可复现S5视觉：桌面、触摸、减少动效与截图', async ({ page }, info) => {
  await setup(page)
  await page.setViewportSize({ width: 1536, height: 1024 })
  await openOverview(page)
  const plot = await page.locator('.overview-chart--sales').boundingBox()
  if (plot)
    await page.mouse.move(plot.x + 40 + ((plot.width - 50) * 6.5) / 7, plot.y + plot.height * 0.5)
  await page.screenshot({ path: info.outputPath('overview-desktop.png') })
  await page.getByRole('button', { name: '销售明细', exact: true }).click()
  await expect(page.getByRole('dialog').locator('tbody tr')).toHaveCount(1)
  await page.screenshot({ path: info.outputPath('overview-detail.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect
    .poll(() =>
      page.locator('.overview-chart').evaluateAll((elements) =>
        elements.every((el) => {
          const svg = el.querySelector('svg')
          return (
            !svg ||
            Math.abs(svg.getBoundingClientRect().width - el.getBoundingClientRect().width) < 2
          )
        }),
      ),
    )
    .toBe(true)
  await page.screenshot({ path: info.outputPath('overview-mobile.png'), fullPage: true })
})

test('时间与现金历史边界：UTC、未知、超过90日、期初缺失及账不平', () => {
  expect(salesRange(null, 7)).toBeNull()
  expect(salesRange('2026-09-09T00:30:00Z', 7)).toEqual({
    from: '2026-09-03T00:00:00.000Z',
    to: '2026-09-10T00:00:00.000Z',
  })
  expect(salesRange('2026-09-09T00:30:00Z', 7, '2026-01-01', '2026-09-09')).toBeNull()
  expect(salesRange('2026-09-09T00:30:00Z', 7, '2026-09-08', '2026-09-10')).toBeNull()
  const d: any = structuredClone(fixture.dashboard),
    l: any = { ...structuredClone(fixture['ledger-entries']), complete: true }
  expect(cashHistory(l, d).map((x) => x.value)).toEqual([100000, 60000, 40000])
  expect(cashHistory({ ...l, complete: false }, d)).toEqual([])
  expect(
    cashHistory({ ...l, items: l.items.filter((x: any) => x.effect_type !== 'INIT') }, d),
  ).toEqual([])
  d.state.cash_minor += 100
  expect(cashHistory(l, d)).toEqual([])
})

test('原方案往返后仍可核对，切换环境自动关闭旧确认框', async ({ page }) => {
  const c = await setup(page)
  c.pendingDecision = true
  await page.goto('/')
  const q = pendingFixture.plan.proposed_purchase.quantity
  const review = page.getByRole('button', { name: `核对 ${q} 件采购`, exact: true })
  await expect(review).toBeVisible()
  await page.locator('.rail .overview-entry').click()
  await expect(page.getByTestId('overview-cash')).toHaveText('¥1,000')
  await page.getByRole('button', { name: '返回今日', exact: true }).click()
  await review.click()
  await expect(page.getByRole('dialog')).toContainText(`核对这笔采购`)
  await expect(page.getByRole('dialog')).toContainText(`${q} 件`)
  c.active = 'overview-fixture-b'
  await expect(page.getByTestId('cash')).toHaveText('¥1,234')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(c.writes).toEqual([])
})

test('生产构建：今日不下载图表引擎，打开概览才加载', async ({ page }) => {
  test.skip(process.env.OVERVIEW_PRODUCTION !== 'true', 'Requires the local production preview.')
  const { readdirSync, statSync } = await import('node:fs')
  const directory = new URL('../.output/public/_nuxt/', import.meta.url)
  const chunks = readdirSync(directory).filter(
    (name) =>
      name.endsWith('.js') &&
      statSync(new URL(name, directory)).size > 500000 &&
      readFileSync(new URL(name, directory), 'utf8').includes('echarts'),
  )
  expect(chunks.length).toBeGreaterThan(0)
  await setup(page)
  const loaded: string[] = []
  page.on('request', (request) => loaded.push(request.url()))
  await page.goto('/')
  await expect(page.locator('.rail .overview-entry')).toBeVisible()
  expect(loaded.some((url) => chunks.some((chunk) => url.endsWith(chunk)))).toBe(false)
  await page.locator('.rail .overview-entry').click()
  await expect(page.locator('.overview-chart--sales svg')).toBeVisible()
  expect(loaded.some((url) => chunks.some((chunk) => url.endsWith(chunk)))).toBe(true)
})

test('初始现金不画假趋势；单独过期的流水在现金区域明确提示', async ({ page }) => {
  const c = await setup(page)
  c.pendingDecision = true
  await page.goto('/?view=overview')
  await expect(page.getByTestId('overview-cash')).toHaveText('¥1,000')
  await expect(page.locator('.overview-cash')).toContainText('尚无现金变更')
  await expect(page.locator('.overview-chart--cash')).toHaveCount(0)
  c.staleLedger = true
  await page.getByRole('button', { name: '刷新经营概览' }).click()
  await expect(page.locator('.overview-cash .overview-inline-warning')).toContainText(
    '资料尚未同步',
  )
})
