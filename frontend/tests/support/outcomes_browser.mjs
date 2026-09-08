import { chromium, expect } from '@playwright/test'
import { writeFile, readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
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
  expect(run.outcomes).toHaveLength(2)
  expect(run.activity.every((a) => a.status === 'SUCCEEDED')).toBe(true)
  expect(events.events.filter((e) => e.type === 'tool.started')).toHaveLength(3)
  expect(events.events.filter((e) => e.type === 'tool.completed')).toHaveLength(3)
  expect(errors).toEqual([])
  const outcomes = page.locator('.agent-outcomes')
  await expect(outcomes).toContainText('试算结果 · 未修改方案')
  await expect(outcomes).toContainText('方案修订回执')
  await page.reload()
  await expect(outcomes).toContainText('方案 v1 → v2')
  await expect(page.locator('.plan-change-receipt')).toContainText('40 → 20')
  await outcomes.locator('summary').first().click()
  await expect(outcomes.locator('table:visible')).toHaveCount(2)
  await outcomes.evaluate((e) => e.scrollIntoView({ block: 'start' }))
  await page.screenshot({ path: output + '/outcomes-desktop.jpg', fullPage: false })
  const source = page.locator('.agent-message .agent-source').first()
  await source.locator('summary').first().click()
  const opener = source.getByRole('button', { name: '打开当时原文片段' })
  await opener.click()
  const dialog = page.getByRole('dialog', { name: '历史原文片段' })
  await expect(dialog).toContainText('原始供应商条款')
  await dialog.evaluate(async (d) => {
    await Promise.all(d.getAnimations().map((a) => a.finished))
  })
  await expect(dialog.locator('.evidence-text')).toContainText(
    '<script>alert("untrusted")</script>',
  )
  expect(await dialog.locator('script').count()).toBe(0)
  const reference = messages.items.find((m) => m.role === 'assistant').references[0]
  const versionPath = `/api/backend/api/v1/documents/${reference.id}/versions/${reference.version_id}`
  const versions = await (
    await page.request.get(base + `/api/backend/api/v1/documents/${reference.id}/versions`)
  ).json()
  expect(versions.items[0].version_no).toBe(2)
  let downloaded = false
  const trackDownload = () => {
    downloaded = true
  }
  page.on('download', trackDownload)
  await page.route('**' + versionPath + '/content', (route) =>
    route.fulfill({ status: 200, body: 'CORRUPTED BY TEST', contentType: 'text/plain' }),
  )
  await dialog.getByRole('button', { name: '下载原件 v1', exact: true }).click()
  await expect(dialog).toContainText('无法下载此历史版本')
  expect(downloaded).toBe(false)
  await page.unroute('**' + versionPath + '/content')
  const downloadReady = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '下载原件 v1', exact: true }).click()
  const saved = await downloadReady
  expect(saved.suggestedFilename()).toBe('notes.txt')
  const bytes = await readFile(await saved.path())
  const version = await (await page.request.get(base + versionPath)).json()
  expect(createHash('sha256').update(bytes).digest('hex')).toBe(version.content_sha256)
  expect(bytes.toString()).toContain('历史条款：最少20件。')
  expect(bytes.toString()).not.toContain('New version')
  page.off('download', trackDownload)
  observations.push(
    'original v1 downloaded with exact filename/bytes/hash despite latest v2; corrupted transfer blocked',
  )

  await page.screenshot({ path: output + '/evidence-desktop.jpg', fullPage: false })
  await page.keyboard.press('Escape')
  await expect(opener).toBeFocused()
  await page.setViewportSize({ width: 390, height: 844 })
  await opener.click()
  await expect(dialog).toBeVisible()
  await dialog.evaluate(async (d) => {
    await Promise.all(d.getAnimations().map((a) => a.finished))
  })
  const bounds = await dialog.boundingBox()
  expect(bounds.y).toBeGreaterThanOrEqual(0)
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(844)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: output + '/evidence-mobile.jpg', fullPage: false })
  await page.keyboard.press('Escape')
  await outcomes.evaluate((e) => e.scrollIntoView({ block: 'start' }))
  await page.screenshot({ path: output + '/outcomes-mobile.jpg', fullPage: false })
  await opener.click()
  await expect(dialog).toContainText('原始供应商条款')
  await control('evidence/archive')
  await expect(dialog).toContainText('历史片段当前不可访问', { timeout: 15000 })
  await expect(dialog.locator('.evidence-text')).toHaveCount(0)
  await page.keyboard.press('Escape')
  observations.push(
    'archiving the actual document cleared an already-open excerpt on the shared refresh cycle',
  )
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.reload()
  await expect(outcomes).toContainText('方案修订回执')
  observations.push(
    'persisted evaluation and v1-to-v2 revision survived refresh; no purchase; safe historical excerpt opened with Escape/focus return on desktop and mobile',
  )
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
