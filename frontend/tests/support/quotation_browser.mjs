import { chromium, expect } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'
const base = process.env.WORK_FRONTEND,
  backend = process.env.WORK_BACKEND
const store = process.env.WORK_STORE,
  output = process.env.WORK_OUTPUT
for (const url of [base, backend])
  if (new URL(url).hostname !== '127.0.0.1') throw Error('Loopback only')
const browser = await chromium.launch({ headless: true }),
  checks = [],
  errors = []
const header = '商品,报价金额,币种,计价单位,每包装件数,最低订购量,MOQ单位,来源'
const csvA = '\ufeff' + header + '\n报价甲,120,CNY,箱,,2,箱,供应商甲'
const csvB = header + '\n果汁,240,CNY,箱,10,1,箱,A供应商\n饮料,180,CNY,箱,15,3,箱,B供应商'
let page, context
async function newContext() {
  context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    reducedMotion: 'reduce',
  })
  page = await context.newPage()
  page.on('pageerror', (e) => errors.push(e.message))
  const response = await page.request.post(base + '/api/session', {
    data: { token: process.env.WORK_AUTH },
  })
  expect(response.ok(), await response.text()).toBe(true)
}
async function read(path) {
  const r = await page.request.get(base + '/api/backend/api/v1/' + path)
  expect(r.ok(), await r.text()).toBe(true)
  return r.json()
}
async function create() {
  await page.goto(base + '/?store=' + store)
  await page
    .getByRole('button', { name: '整理一份供应商报价 查看单件价、包装、起订量与来源', exact: true })
    .click()
  await page.getByRole('button', { name: '开始报价事项', exact: true }).click()
  await expect(page.locator('.work-detail')).toBeVisible()
  return page.locator('.work-detail').getAttribute('data-work-id')
}
async function upload(filename, content) {
  await page.locator('.quotation-attachment summary').click()
  await page
    .getByLabel('上传报价 CSV', { exact: true })
    .setInputFiles({ name: filename, mimeType: 'text/csv', buffer: Buffer.from(content) })
}
async function snapshot(name) {
  await page.screenshot({ path: output + '/' + name + '.png', fullPage: true })
}
try {
  await newContext()
  const a = await create()
  let lost = false
  await page.route('**/quotation-files', async (route) => {
    if (route.request().method() === 'POST' && !lost) {
      lost = true
      expect((await route.fetch()).ok()).toBe(true)
      return route.abort('connectionreset')
    }
    return route.continue()
  })
  await upload('报价甲.csv', csvA)
  await expect(page.getByRole('button', { name: '查询并重试原提交', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: '查询并重试原提交', exact: true }).click()
  await expect(page.locator('.quotation-workspace')).toContainText('报价甲.csv')
  expect((await read('work-items/' + a + '/quotation-files')).items).toHaveLength(1)
  const panel = page.locator('.quotation-workspace')
  await panel.getByRole('button', { name: '仅更新本次结果', exact: true }).click()
  await expect(panel.getByRole('cell', { name: /暂不能计算/ })).toBeVisible()
  const first = (await read('work-items/' + a + '/quotation-results')).items[0]
  expect(first.rows[0].unit_price).toBeNull()
  expect(first.rows[0].moq_pieces).toBeNull()
  await panel.getByLabel('正确值', { exact: true }).fill('12')
  await panel.getByLabel('整理顺序', { exact: true }).selectOption('unit_price')
  await panel.getByRole('button', { name: '更新并记住整理顺序', exact: true }).click()
  await expect(panel.getByRole('cell', { name: /10 CNY/ })).toBeVisible()
  await expect(panel).toContainText('折合 24 件')
  const versionsA = (await read('work-items/' + a + '/quotation-results')).items
  expect(versionsA).toHaveLength(2)
  const corrected = versionsA.find((r) => r.version === 2)
  expect(corrected.rows[0].unit_price).toBe('10')
  expect(corrected.rows[0].moq_pieces).toBe('24')
  const rule = await read('work-items/' + a + '/quotation-rule')
  expect(rule.rule.sort_by).toBe('unit_price')
  expect(rule.rule.validated).toBe(true)
  const original = page.waitForEvent('download')
  await panel.getByRole('link', { name: '下载原件', exact: true }).click()
  const originalDownload = await original
  expect(await readFile(await originalDownload.path(), 'utf8')).toBe(csvA)
  const exported = page.waitForEvent('download')
  await panel.getByRole('link', { name: '下载此版本 CSV', exact: true }).click()
  const download = await exported
  const exportedText = await readFile(await download.path(), 'utf8')
  expect(exportedText).toContain('10')
  expect(exportedText).toContain('24')
  await snapshot('quotation-a-corrected')
  checks.push(
    'Q1/Q2: committed upload survives lost response and refresh without duplicate; missing pack stays unknown; real backend correction returns 10 CNY and MOQ 24; authorized original and result downloads',
  )
  await context.close()
  await newContext()
  await page.goto(base + '/?view=work&item=' + a + '&store=' + store)
  await expect(
    page.locator('.quotation-workspace').getByRole('cell', { name: /10 CNY/ }),
  ).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('ss.local-quotes.v1'))).toBeNull()
  await page
    .locator('.quotation-workspace')
    .getByLabel('结果版本', { exact: true })
    .selectOption(first.id)
  await expect(
    page.locator('.quotation-workspace').getByRole('cell', { name: /暂不能计算/ }),
  ).toBeVisible()
  const b = await create()
  await upload('报价乙.csv', csvB)
  const secondPanel = page.locator('.quotation-workspace')
  await expect(secondPanel).toContainText('报价乙.csv')
  await expect(secondPanel.getByLabel('整理顺序', { exact: true })).toHaveValue('unit_price')
  await secondPanel.getByRole('button', { name: '仅更新本次结果', exact: true }).click()
  await expect(secondPanel.getByRole('cell', { name: /12 CNY/ })).toBeVisible()
  await expect(secondPanel).toContainText('折合 45 件')
  const resultB = (await read('work-items/' + b + '/quotation-results')).items[0]
  expect(resultB.rows.map((row) => row.product)).toEqual(['饮料', '果汁'])
  expect(resultB.rows.map((row) => row.source)).toEqual(['B供应商', 'A供应商'])
  await expect(secondPanel.locator('tbody tr').first()).toContainText('饮料')
  expect(resultB.rows[1].unit_price).toBe('24')
  expect(resultB.rows[1].moq_pieces).toBe('10')
  expect(resultB.rows[0].unit_price).toBe('12')
  expect(resultB.rows[0].moq_pieces).toBe('45')
  expect(resultB.rule.version).toBe(rule.rule.version)
  expect(resultB.rule.source).toEqual(rule.rule.source)
  expect(resultB.input_sha256).not.toBe(corrected.input_sha256)
  expect(resultB.corrections).toEqual([])
  checks.push(
    'Q3: new browser context reads original and immutable old versions from server; new Work applies saved sorting to B, recomputes 12 CNY / 45 units, and never transfers A field values',
  )
  await secondPanel.getByLabel('整理顺序', { exact: true }).selectOption('source')
  await secondPanel.getByRole('button', { name: '仅更新本次结果', exact: true }).click()
  await expect(secondPanel.locator('tbody tr').first()).toContainText('果汁')
  const resultB2 = (await read('work-items/' + b + '/quotation-results')).items.find(
    (result) => result.version === 2,
  )
  expect(resultB2.rows.map((row) => row.product)).toEqual(['果汁', '饮料'])
  expect(resultB2.rows.map((row) => row.unit_price)).toEqual(['24', '12'])
  const latestRule = await read('work-items/' + b + '/quotation-rule')
  expect(latestRule.rule.version).toBe(rule.rule.version)
  expect(latestRule.rule.sort_by).toBe('unit_price')
  expect(latestRule.rule.source).toEqual(rule.rule.source)
  checks.push(
    'One-off source sorting changes only B version 2; saved unit-price rule, source receipts and previous B version remain unchanged',
  )
  await secondPanel.getByText('已保存的报价整理规则', { exact: true }).click()
  await secondPanel.getByRole('button', { name: '撤回要求', exact: true }).click()
  await expect.poll(async () => (await read('work-items/' + b + '/quotation-rule')).rule).toBeNull()
  const historicalB = (await read('work-items/' + b + '/quotation-results')).items[0]
  expect(historicalB.rule.version).toBe(latestRule.rule.version)
  await page.setViewportSize({ width: 390, height: 844 })
  await snapshot('quotation-b-mobile')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  )
  expect((await read('actions?store_id=' + store)).items).toHaveLength(0)
  expect(errors).toEqual([])
  checks.push(
    'Q4: rule withdrawal is persisted, prior result rule snapshot stays unchanged; mobile width valid; purchases zero',
  )
  await writeFile(
    output + '/results.json',
    JSON.stringify(
      { checks, errors, store, work_a: a, work_b: b, model_calls: 0, purchases: 0 },
      null,
      2,
    ),
  )
} catch (e) {
  if (page && !page.isClosed()) await snapshot('quotation-failure')
  throw e
} finally {
  await browser.close()
}
