import { chromium, expect } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'
const base = process.env.WORK_FRONTEND,
  store = process.env.WORK_STORE,
  output = process.env.WORK_OUTPUT
if (new URL(base).hostname !== '127.0.0.1') throw Error('Loopback only')
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({
  viewport: { width: 1440, height: 1050 },
  reducedMotion: 'reduce',
})
const errors = [],
  checks = []
page.on('pageerror', (e) => errors.push(e.message))
async function get(path) {
  const r = await page.request.get(base + '/api/backend/api/v1/' + path)
  expect(r.ok(), await r.text()).toBe(true)
  return r.json()
}
async function state() {
  return (await get('dashboard?store_id=' + store)).state
}
async function detail(id) {
  return get('work-items/' + id)
}
try {
  expect(
    (
      await page.request.post(base + '/api/session', { data: { token: process.env.WORK_AUTH } })
    ).ok(),
  ).toBe(true)
  await page.goto(base + '/?store=' + store)
  await expect(page.getByRole('button', { name: '先试算补货', exact: true })).toBeVisible()
  const before = await state()
  await page.getByRole('button', { name: '先试算补货', exact: true }).click()
  await expect(page.getByRole('heading', { name: '先试算补货', exact: true })).toBeVisible()
  await page.getByLabel('现金至少保留（元）', { exact: true }).fill('750.00')
  await page.getByLabel('比较数量（件，以逗号分隔）').fill('0, 20, 40, 80')
  await page.screenshot({ path: output + '/form.png' })
  let lost = false
  const keys = []
  await page.route('**/api/backend/api/v1/stores/*/simulations', async (route) => {
    keys.push(route.request().headers()['idempotency-key'])
    if (!lost) {
      lost = true
      await route.fetch()
      return route.abort('connectionreset')
    }
    return route.continue()
  })
  await page.getByRole('button', { name: '比较并保存结果', exact: true }).click()
  await expect(page.getByRole('button', { name: '查询并重试原试算', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: '先试算补货', exact: true }).click()
  await page.getByRole('button', { name: '查询并重试原试算', exact: true }).click()
  await expect(page.locator('.work-detail')).toBeVisible()
  const id = await page.locator('.work-detail').getAttribute('data-work-id')
  const saved = await detail(id)
  expect(saved.item.result.calculation.recommended_candidate_id).toBe('candidate_20')
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBe(keys[1])
  expect((await get('work-items?store_id=' + store)).items).toHaveLength(1)
  expect(await state()).toEqual(before)
  expect((await get('missions?store_id=' + store)).items).toHaveLength(0)
  expect((await get('actions?store_id=' + store)).items).toHaveLength(0)
  await expect(page.getByLabel('推荐候选的代价').first()).toContainText('20 件')
  await expect(page.getByLabel('推荐候选的代价').first()).toContainText('¥800')
  checks.push(
    'real POST commit, lost response, refresh and same-key retry keep exactly one result and zero business writes',
  )
  await page.screenshot({ path: output + '/comparison.png', fullPage: true })
  const result = page.locator('.work-status-panel > .work-result')
  for (const [label, file] of [
    ['保存结果', 'result.txt'],
    ['下载 CSV（含依据）', 'result.csv'],
    ['下载原始计算数据', 'result.json'],
  ]) {
    const downloading = page.waitForEvent('download')
    await result.getByRole('button', { name: label, exact: true }).click()
    const download = await downloading
    expect(download.suggestedFilename()).toContain(saved.item.result.provenance.result_id)
    await download.saveAs(output + '/' + file)
  }
  const text = await readFile(output + '/result.txt', 'utf8')
  for (const value of [
    '现金底线：750.00元',
    '采购数量（件）',
    '业务截至',
    '合成模拟环境',
    'finite-candidates-v1',
    saved.item.result.calculation.input_hash,
  ])
    expect(text).toContain(value)
  const csv = await readFile(output + '/result.csv', 'utf8')
  expect(csv).toContain('输入假设')
  expect(csv).toContain('750.00')
  const raw = JSON.parse(await readFile(output + '/result.json', 'utf8'))
  expect(raw.result.calculation.input.policy.cash_floor_minor).toBe(75000)
  expect(raw.result.calculation.candidates[1].spend_minor).toBe(20000)
  checks.push(
    'authorized TXT/CSV/JSON downloads preserve same immutable result, assumptions, provenance and integer money',
  )
  await page.reload()
  await expect(page.getByLabel('推荐候选的代价').first()).toContainText('20 件')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: output + '/mobile.png', fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(
    true,
  )
  checks.push('result survives refresh and narrow viewport has no page overflow')
  await page.setViewportSize({ width: 1440, height: 1050 })
  await page.getByRole('button', { name: '调整条件再试算', exact: true }).click()
  await page.getByLabel('比较数量（件，以逗号分隔）').fill('0, 20, 40, 80, 100')
  await page.getByRole('button', { name: '比较并保存结果', exact: true }).click()
  await expect(page.locator('.work-detail')).toHaveAttribute('data-work-id', id)
  await expect(result.locator('tbody tr')).toHaveCount(5)
  const revised = await detail(id)
  expect(revised.item.version).toBe(2)
  expect(revised.messages.filter((m) => m.result)).toHaveLength(2)
  expect((await get('work-items?store_id=' + store)).items).toHaveLength(1)
  const oldExport = await get(`work-items/${id}/results/${saved.item.result.provenance.result_id}`)
  expect(oldExport.is_latest_result).toBe(false)
  expect(oldExport.result).toEqual(saved.item.result)
  checks.push(
    'changing assumptions updates the same work, preserves the previous immutable result and avoids duplicate cards',
  )
  await page.getByRole('button', { name: '按这些条件开始跟进', exact: true }).click()
  await expect(page.locator('.task-workspace')).toBeVisible()
  const accepted = await detail(id)
  expect(accepted.item.mission.policy.cash_floor_minor).toBe(75000)
  expect((await get('missions?store_id=' + store)).items).toHaveLength(1)
  expect((await get('actions?store_id=' + store)).items).toHaveLength(0)
  expect(await state()).toEqual(before)
  checks.push(
    'explicit user conversion creates one Mission with the reviewed floor and no purchase',
  )
  expect(errors).toEqual([])
  await writeFile(
    output + '/result-checks.json',
    JSON.stringify(
      {
        checks,
        pageErrors: errors,
        store,
        workId: id,
        resultId: saved.item.result.provenance.result_id,
        businessStateUnchanged: true,
        modelCalls: 0,
      },
      null,
      2,
    ),
  )
  console.log(JSON.stringify({ passed: checks.length, checks }))
} finally {
  await browser.close()
}
