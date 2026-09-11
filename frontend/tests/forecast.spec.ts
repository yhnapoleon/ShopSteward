import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const fixture = JSON.parse(
  readFileSync(new URL('./fixtures/overview.json', import.meta.url), 'utf8'),
)
const model = {
  model_version: 'v6-test',
  feature_profile: 'v6',
  minimum_history_days: 84,
  recommended_history_days: 374,
  weights: {},
  evaluation: {},
  limitations: [],
  supported_series: [
    {
      series_id: 'FOODS_1_CA_1',
      item_id: 'FOODS_1',
      store_id: 'CA_1',
      dept_id: 'FOODS',
      cat_id: 'FOODS',
      state_id: 'CA',
    },
  ],
}
function result(store: string, status = 'READY') {
  return {
    store_id: store,
    sku_id: fixture.dashboard.state.stocks[0].sku_id,
    status,
    reason:
      status === 'STALE'
        ? '经营状态已变化'
        : status === 'READY'
          ? 'HISTORICAL_DEMO_ONLY: original historical dates; not current store demand'
          : null,
    mode: 'historical_demo',
    usable_for_planning: false,
    model,
    history: [],
    forecast:
      status === 'UNAVAILABLE'
        ? null
        : {
            forecast_id: 'forecast-' + store,
            model_version: 'v6-test',
            series_id: 'FOODS_1_CA_1',
            store_id: store,
            sku_id: fixture.dashboard.state.stocks[0].sku_id,
            observation_end_date: '2016-03-27',
            horizon_start: '2016-03-28',
            horizon_end: '2016-04-03',
            daily_predictions: Array.from({ length: 7 }, (_, i) => ({
              date: `2016-0${i < 4 ? '3-' + (28 + i) : '4-0' + (i - 3)}`,
              quantity: i + 0.1,
            })),
            predicted_quantity: 22,
            total_quantity_raw: 21.7,
            generated_at: '2026-09-11T00:00:00Z',
            valid_until: '2099-09-12T00:00:00Z',
            assumptions: [],
            evaluation: {},
          },
  }
}
async function setup(page: Page, role = 'admin', initial = 'UNAVAILABLE') {
  const control = {
    active: 'overview-fixture-a',
    sku: 'sku_001',
    status: initial,
    writes: [] as any[],
    delay: null as Promise<void> | null,
    reference: '',
    activated: false,
    mode: 'historical_demo',
  }
  await page.route('**/api/**', async (route) => {
    const req = route.request(),
      url = new URL(req.url())
    const path = url.pathname.replace('/api/backend/api/v1/', '')
    if (url.pathname === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: 'forecast-test',
          roles: [role],
          agentEnabled: true,
          devTools: true,
        },
      })
    const id = url.searchParams.get('store_id') || control.active
    const f = JSON.parse(
      JSON.stringify(fixture)
        .replaceAll('overview-fixture-a', id)
        .replaceAll('sku_001', control.sku),
    )
    if (path === 'stores')
      return route.fulfill({
        json: {
          items: ['overview-fixture-a', 'overview-fixture-b'].map((store_id) => ({
            store_id,
            simulation_time: '2026-09-11T00:00:00Z',
          })),
          active_store: { store_id: control.active },
          next_cursor: null,
        },
      })
    if (path.endsWith('/forecast/model')) return route.fulfill({ json: model })
    if (/stores\/[^/]+\/forecast/.test(path)) {
      const store = path.split('/')[1]!
      const sku =
        req.method() === 'POST' ? req.postDataJSON().sku_id : url.searchParams.get('sku_id')
      if (req.method() === 'POST') {
        control.writes.push(req.postDataJSON())
        const delay = control.delay
        if (delay) await delay
        control.status = 'READY'
      }
      const value = result(store, control.status)
      Object.assign(value, { activate_for_planning: control.activated, mode: control.mode })
      value.sku_id = sku
      if (value.forecast) value.forecast.sku_id = sku
      return route.fulfill({ json: value })
    }
    if (path.includes('/conversations'))
      return route.fulfill({
        json: {
          items: control.reference
            ? [{ id: 'forecast-conversation', is_default: true, active_run_id: null }]
            : [],
          next_cursor: null,
        },
      })
    if (path.includes('/messages'))
      return route.fulfill({
        json: {
          items: [
            {
              id: 'forecast-message',
              role: 'assistant',
              run_id: null,
              content: '请核对预测依据。',
              references: [
                {
                  type: 'forecast',
                  id: control.reference,
                  version: 'v6-test',
                  store_id: control.active,
                  sku_id: control.sku,
                },
              ],
            },
          ],
          next_after_seq: null,
        },
      })
    if (path.includes('/timeline'))
      return route.fulfill({ json: f.timeline || { items: [], next_cursor: null } })
    if (path.startsWith('plans/')) return route.fulfill({ json: f.plan })
    if (f[path]) return route.fulfill({ json: f[path] })
    return route.fulfill({ json: { items: [], next_cursor: null } })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '七日需求预测' })).toBeVisible()
  return control
}

test('forecast unavailable is empty; model scenario keeps exact dates in expandable evidence', async ({
  page,
}) => {
  const control = await setup(page)
  const panel = page.getByRole('region', { name: '七日需求预测' })
  await expect(panel).toContainText('UNAVAILABLE')
  await expect(panel.getByTestId('forecast-total')).toHaveCount(0)
  await panel.getByLabel('模型参考系列').selectOption('FOODS_1_CA_1')
  await panel.getByRole('button', { name: '运行模型推演' }).click()
  await expect(panel).toContainText('READY')
  await expect(panel.getByTestId('forecast-total')).toHaveText('22 件')
  await expect(panel.getByRole('table', { name: '七日逐日预测' }).getByRole('row')).toHaveCount(8)
  await expect(panel).toContainText('模型推演，仅供参考')
  await expect(panel).not.toContainText('HISTORICAL_DEMO_ONLY')
  await expect(panel.getByText('观察截至 2016-03-27', { exact: true })).not.toBeVisible()
  await expect(panel.getByRole('table', { name: '七日逐日预测' })).toContainText('03-28')
  await expect(panel.getByRole('table', { name: '七日逐日预测' })).not.toContainText('2016')
  await panel.getByText('版本与可追溯依据', { exact: true }).click()
  await expect(panel.getByText('观察截至 2016-03-27', { exact: true })).toBeVisible()
  await expect(panel.getByText('预测范围 2016-03-28 至 2016-04-03', { exact: true })).toBeVisible()
  await expect(panel).toContainText('0.57%')
  expect(control.writes[0]).toMatchObject({ mode: 'historical_demo', activate_for_planning: false })
})

test('viewer can read stale evidence but cannot refresh', async ({ page }) => {
  const control = await setup(page, 'viewer', 'STALE')
  const panel = page.getByRole('region', { name: '七日需求预测' })
  await expect(panel).toContainText('STALE')
  await expect(panel).toContainText('经营状态已变化')
  await expect(panel.getByRole('button', { name: '运行模型推演' })).toHaveCount(0)
  expect(control.writes).toEqual([])
})

test('switching store discards an in-flight refresh response', async ({ page }) => {
  const control = await setup(page)
  let release!: () => void
  control.delay = new Promise((resolve) => {
    release = resolve
  })
  await page.getByLabel('模型参考系列').selectOption('FOODS_1_CA_1')
  await page.getByRole('button', { name: '运行模型推演' }).click()
  await expect.poll(() => control.writes.length).toBe(1)
  control.active = 'overview-fixture-b'
  await expect(page.getByRole('region', { name: '七日需求预测' })).toContainText(
    'overview-fixture-b',
  )
  release()
  await expect(page.getByTestId('forecast-total')).toHaveCount(0)
  await expect(page.getByRole('region', { name: '七日需求预测' })).not.toContainText(
    'forecast-overview-fixture-a',
  )
})

test('observed history validation blocks missing days and activation requires explicit choice', async ({
  page,
}) => {
  const control = await setup(page)
  await page.getByLabel('输入来源', { exact: true }).selectOption('observed')
  await page.getByLabel('模型参考系列').selectOption('FOODS_1_CA_1')
  await page.getByLabel('完整销售历史 JSON').fill('[]')
  await page.getByRole('button', { name: '导入并运行预测' }).click()
  await expect(page.getByRole('alert')).toContainText('84–374')
  expect(control.writes).toHaveLength(0)
  const history = Array.from({ length: 84 }, (_, i) => ({
    date: new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10),
    sold_quantity: 3,
    complete: true,
  }))
  await page.getByLabel('完整销售历史 JSON').fill(JSON.stringify(history))
  await page.getByLabel('观察截至日', { exact: true }).fill(history.at(-1)!.date)
  for (const invalidQuantity of [0.5, 1000000001]) {
    await page
      .getByLabel('完整销售历史 JSON')
      .fill(
        JSON.stringify(
          history.map((row, i) => (i === 0 ? { ...row, sold_quantity: invalidQuantity } : row)),
        ),
      )
    await page.getByRole('button', { name: '导入并运行预测' }).click()
    await expect(page.getByRole('alert')).toContainText('整数')
    expect(control.writes).toHaveLength(0)
  }
  await page.getByLabel('完整销售历史 JSON').fill(JSON.stringify(history))
  await expect(page.getByRole('checkbox')).not.toBeChecked()
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: '导入并运行预测' }).click()
  await expect.poll(() => control.writes.length).toBe(1)
  expect(control.writes[0]).toMatchObject({
    mode: 'observed',
    activate_for_planning: true,
    history,
  })
  await page.getByLabel('输入来源', { exact: true }).selectOption('historical_demo')
  await expect(page.getByRole('checkbox')).toHaveCount(0)
})

test('Agent forecast reference opens the panel and identifies superseded evidence', async ({
  page,
}) => {
  const control = await setup(page, 'admin', 'READY')
  control.reference = 'older-forecast-id'
  await page.reload()
  await page.getByRole('button', { name: '查看预测依据 · v6-test', exact: true }).click()
  const panel = page.getByRole('region', { name: '七日需求预测' })
  await expect(panel).toContainText('正在核对引用：older-forecast-id')
  await expect(panel).toContainText('该引用已被更新或当前不可用')
})

test('reusing observed input preserves explicit planning activation even when not currently usable', async ({
  page,
}) => {
  const control = await setup(page, 'admin', 'STALE')
  control.activated = true
  control.mode = 'observed'
  await page.reload()
  await page
    .getByRole('button', { name: '复用已保存输入运行（保持规划启用）', exact: true })
    .click()
  await expect.poll(() => control.writes.length).toBe(1)
  expect(control.writes[0]).toEqual({ sku_id: 'sku_001', activate_for_planning: true })
})

test('switching SKU clears the old forecast and imported draft', async ({ page }) => {
  const control = await setup(page, 'admin', 'READY')
  await page.getByLabel('输入来源', { exact: true }).selectOption('observed')
  await page.getByLabel('完整销售历史 JSON').fill('old SKU draft')
  control.sku = 'sku_002'
  control.status = 'UNAVAILABLE'
  const panel = page.getByRole('region', { name: '七日需求预测' })
  await expect(panel).toContainText('商品 sku_002')
  await expect(panel.getByTestId('forecast-total')).toHaveCount(0)
  await page.getByLabel('输入来源', { exact: true }).selectOption('observed')
  await expect(page.getByLabel('完整销售历史 JSON')).toHaveValue('')
})
