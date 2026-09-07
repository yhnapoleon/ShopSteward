import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'

test.skip(
  process.env.ENVIRONMENT_E2E !== 'true',
  'Run through verify_environment_sync.py on isolated databases',
)

test('模拟器创建切换后端环境，旧前端自动换场景、同步事件并绑定真实Agent', async ({
  page,
  context,
}, info) => {
  test.setTimeout(300000)
  await page.request.post('/api/session', { data: { token: process.env.ENVIRONMENT_TEST_TOKEN } })
  await page.goto('/?view=today')
  await page.getByRole('button', { name: '联调控制 · 合成数据', exact: true }).click()
  await page.getByRole('button', { name: '创建新的 SC-01 场景', exact: true }).click()
  await expect(page.getByTestId('cash')).toHaveText('¥1,000')
  await page.getByRole('button', { name: '开始备货跟进', exact: true }).click()
  await page.getByRole('button', { name: '按以上条件开始', exact: true }).click()
  await expect(page.getByRole('button', { name: '核对 40 件采购', exact: true })).toBeVisible()
  const previous = (await (await page.request.get('/api/backend/api/v1/stores')).json())
    .active_store.store_id
  await page.getByRole('button', { name: '核对 40 件采购', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  const simulator = await context.newPage()
  await simulator.goto(process.env.SIMULATOR_URL + '/console/')
  await expect(simulator.locator('input[name="create-mode"][value="linked"]')).toBeChecked()
  await simulator.locator('#scenario-type').selectOption('SANDBOX')
  await simulator.locator('#seed-cash').fill('1234')
  await simulator.locator('#seed-stock').fill('37')
  await simulator.locator('#seed-label').fill('Environment sync E2E')
  await simulator.locator('#create-run-submit').click()
  // No reload, store selection, URL change or browser-storage signal on the product page.
  await expect(page.getByTestId('cash')).toHaveText('¥1,234')
  await expect(page.getByTestId('stock')).toHaveText('37')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '开始备货跟进', exact: true })).toBeVisible()
  const current = (await (await page.request.get('/api/backend/api/v1/stores')).json()).active_store
    .store_id
  expect(current).not.toBe(previous)
  expect(
    (await (await page.request.get(`/api/backend/api/v1/actions?store_id=${previous}`)).json())
      .items,
  ).toHaveLength(0)

  await simulator.locator('#sale-quantity').fill('3')
  await simulator.locator('#sale-price').fill('20')
  await simulator.locator('#sale-form button[type="submit"]').click()
  await expect(page.getByTestId('stock')).toHaveText('34')
  await expect(page.getByTestId('receivables')).toHaveText('¥60')
  await expect(page.getByTestId('cash')).toHaveText('¥1,234')
  await page.reload()
  await expect(page.getByTestId('stock')).toHaveText('34')

  await page.getByRole('button', { name: '开始备货跟进', exact: true }).click()
  await page.getByRole('button', { name: '按以上条件开始', exact: true }).click()
  const input = page.getByLabel('追问这项备货任务', { exact: true })
  await expect(input).toBeEnabled()
  await input.fill(
    '请调用get_dashboard读取当前店铺最新状态，只报告现金、现货和应收，不修改方案或采购。',
  )
  const accepted = page.waitForResponse(
    (r) => r.request().method() === 'POST' && /\/conversations\/[^/]+\/messages$/.test(r.url()),
  )
  await page.getByRole('button', { name: '发送卡片内消息', exact: true }).click()
  const runId = (await (await accepted).json()).agent_run_id
  let run: any
  await expect
    .poll(
      async () => {
        run = await (await page.request.get('/api/backend/api/v1/agent-runs/' + runId)).json()
        return run.status
      },
      { timeout: 110000, intervals: [1500] },
    )
    .toBe('SUCCEEDED')
  expect(run.output.model).toBe('gpt-5.6-luna')
  expect(run.tools.some((tool: any) => tool.tool === 'get_dashboard' && tool.ok)).toBe(true)
  expect(run.output.content.replaceAll(',', '')).toContain('1234')
  expect(run.output.content).toContain('34')
  const missions = (
    await (await page.request.get(`/api/backend/api/v1/missions?store_id=${current}`)).json()
  ).items
  const conversations = (
    await (
      await page.request.get(
        `/api/backend/api/v1/missions/${missions[0].id}/conversations?limit=100`,
      )
    ).json()
  ).items
  expect(conversations.some((c: any) => c.id === run.conversation_id)).toBe(true)
  await fs.writeFile(
    info.outputPath('environment-sync.json'),
    JSON.stringify({ previous, current, run }, null, 2),
  )
  await info.attach('environment-sync', {
    body: JSON.stringify({ previous, current, run }),
    contentType: 'application/json',
  })
})
