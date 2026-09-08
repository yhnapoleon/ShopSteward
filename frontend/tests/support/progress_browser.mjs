import { chromium, expect } from '@playwright/test'
import { writeFile } from 'node:fs/promises'
const base = process.env.PROGRESS_FRONTEND,
  backend = process.env.PROGRESS_BACKEND,
  output = process.env.PROGRESS_OUTPUT
for (const url of [base, backend])
  if (new URL(url).hostname !== '127.0.0.1') throw new Error('Loopback-only acceptance')
const browser = await chromium.launch({ headless: true })
const observations = []
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const login = await page.request.post(base + '/api/session', {
    data: { token: process.env.PROGRESS_AUTH },
  })
  expect(login.ok()).toBe(true)
  await page.goto(
    base +
      '/?view=task&mission=' +
      process.env.PROGRESS_MISSION +
      '&store=' +
      process.env.PROGRESS_STORE +
      '&panel=agent',
  )
  await expect(page.getByLabel('追问这项备货任务', { exact: true })).toBeEnabled({ timeout: 20000 })
  await page
    .getByLabel('追问这项备货任务', { exact: true })
    .fill('这次修改方案，最多采购20件，采购前让我确认。')
  await page.getByRole('button', { name: '发送卡片内消息', exact: true }).click()
  const step = (name) => page.locator(`[data-invocation="live-${name}"] .tool-state`)
  const control = async (name) => {
    const response = await page.request.post(backend + '/__test__/' + name, {
      headers: { Authorization: 'Bearer ' + process.env.PROGRESS_AUTH },
    })
    expect(response.ok()).toBe(true)
  }
  await expect(step('get_dashboard')).toHaveText('进行中', { timeout: 20000 })
  await expect(page.locator('.agent-stream-note')).toHaveText('实时更新', { timeout: 10000 })
  await expect(page.locator('.agent-run-status')).toContainText('正在核对现金、库存与在途')
  observations.push('real tool.started reached the browser before the tool was released')
  await page.screenshot({
    path: output + '/live-start-desktop.jpg',
    type: 'jpeg',
    quality: 85,
    fullPage: false,
  })
  await page.reload()
  await expect(step('get_dashboard')).toHaveText('进行中', { timeout: 15000 })
  observations.push('refresh restored the original running invocation')
  await control('release/get_dashboard')
  await expect(step('evaluate_plan')).toHaveText('进行中', { timeout: 15000 })
  await expect(step('get_dashboard')).toHaveText('已完成')
  await control('stream/off')
  await expect(page.locator('.agent-stream-note')).toContainText('定期同步', { timeout: 15000 })
  await control('release/evaluate_plan')
  await expect(step('revise_plan')).toHaveText('进行中', { timeout: 15000 })
  await expect(step('evaluate_plan')).toHaveText('已完成')
  observations.push('snapshot polling continued real progress while SSE was unavailable')
  await control('stream/on')
  await expect(page.locator('.agent-stream-note')).toHaveText('实时更新', { timeout: 20000 })
  await control('release/revise_plan')
  await expect(step('revise_plan')).toHaveText('已完成', { timeout: 15000 })
  await expect(page.locator('.agent-run-status')).toContainText('本轮工作已完成', {
    timeout: 15000,
  })
  await expect(page.getByRole('button', { name: '核对 20 件采购', exact: true })).toBeVisible()
  await expect(page.getByTestId('cash')).toHaveText('¥1,000')
  const actions = await (
    await page.request.get(
      base + '/api/backend/api/v1/actions?store_id=' + process.env.PROGRESS_STORE,
    )
  ).json()
  expect(actions.items).toHaveLength(0)
  const conversations = await (
    await page.request.get(
      base + '/api/backend/api/v1/missions/' + process.env.PROGRESS_MISSION + '/conversations',
    )
  ).json()
  const messages = await (
    await page.request.get(
      base +
        '/api/backend/api/v1/conversations/' +
        conversations.items[0].id +
        '/messages?limit=100',
    )
  ).json()
  expect(messages.items.filter((m) => m.role === 'user')).toHaveLength(1)
  const rid = messages.items.find((m) => m.run_id).run_id
  const run = await (await page.request.get(base + '/api/backend/api/v1/agent-runs/' + rid)).json()
  const events = await (
    await page.request.get(base + '/api/backend/api/v1/agent-runs/' + rid + '/events')
  ).json()
  expect(run.activity).toHaveLength(3)
  expect(run.activity.every((a) => a.status === 'SUCCEEDED')).toBe(true)
  expect(events.events.filter((e) => e.type === 'tool.started')).toHaveLength(3)
  expect(events.events.filter((e) => e.type === 'tool.completed')).toHaveLength(3)
  expect(errors).toEqual([])
  await page.screenshot({
    path: output + '/live-completed-desktop.jpg',
    type: 'jpeg',
    quality: 85,
    fullPage: false,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: output + '/live-completed-mobile.jpg',
    type: 'jpeg',
    quality: 85,
    fullPage: false,
  })
  observations.push('real plan revision reached the UI, with no purchase and cash unchanged')
  await writeFile(
    output + '/result.json',
    JSON.stringify(
      {
        observations,
        run,
        events,
        actions: actions.items,
        browserErrors: errors,
        model: 'controlled executor; no model call',
      },
      null,
      2,
    ),
  )
  console.log(JSON.stringify({ status: 'passed', observations }))
} finally {
  await browser.close()
}
