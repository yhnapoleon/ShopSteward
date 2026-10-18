// Run only against the explicit isolated fixture made by the next-phase harness.
// Real HTTP/API/database; no request interception and no model or supplier call.
import { chromium, expect } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'
const base = process.env.RECOVERY_FRONTEND
if (!base || new URL(base).hostname !== '127.0.0.1')
  throw Error('An explicit loopback test URL is required')
const state = JSON.parse(await readFile(process.env.RECOVERY_FIXTURE, 'utf8'))
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({
  viewport: { width: 1440, height: 1100 },
  reducedMotion: 'reduce',
})
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
const prefix = base + '/api/backend/api/v1/'
const read = async (path) => {
  const response = await page.request.get(prefix + path)
  expect(response.ok(), await response.text()).toBe(true)
  return response.json()
}
try {
  const login = await page.request.post(base + '/api/session', {
    data: { token: process.env.RECOVERY_TEST_TOKEN },
  })
  expect(login.ok()).toBe(true)
  const identity = await (await page.request.get(base + '/api/session')).json()
  expect(identity.recoveryCases).toBe(true)
  await page.goto(`${base}/?view=task&store=${state.store_id}&mission=${state.mission_id}`)
  await page.getByRole('button', { name: '供应异常应对', exact: true }).click()
  await expect(page.getByLabel('本次应急预算（元）', { exact: true })).toHaveValue('300.00')
  await page.getByRole('button', { name: '按新要求重新分析', exact: true }).click()
  const casePath = 'operations-cases/' + state.case_id
  await expect.poll(async () => (await read(casePath)).status).toBe('OPTIONS_READY')
  let detail = await read(casePath)
  const b = detail.proposal.candidates.find((c) => c.supplier_id === 'B' && c.quantity === 20)
  expect(detail.proposal.recommended_candidate_id).toBe(b.id)
  expect(b.spend_minor).toBe(24000)
  expect(b.lost_qty).toBe(0)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('200')
  await page.getByRole('button', { name: '按新要求重新分析', exact: true }).click()
  await expect.poll(async () => (await read(casePath)).budget_minor).toBe(20000)
  await expect.poll(async () => (await read(casePath)).status).toBe('OPTIONS_READY')
  await expect(
    page
      .locator(`[data-recovery-candidate="${b.id}"]`)
      .getByRole('button', { name: '生成待确认方案' }),
  ).toBeDisabled()
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '按新要求重新分析', exact: true }).click()
  await expect
    .poll(async () => {
      const value = await read(casePath)
      return value.budget_minor === 30000 && value.status === 'OPTIONS_READY'
    })
    .toBe(true)
  await page
    .locator(`[data-recovery-candidate="${b.id}"]`)
    .getByRole('button', { name: '生成待确认方案' })
    .click()
  await expect(page.locator('.decision-card')).toContainText('¥240')
  detail = await read(casePath)
  expect(detail.plan_status).toBe('PENDING_APPROVAL')
  const actions = await read('actions?store_id=' + state.store_id)
  expect(actions.items).toHaveLength(0)
  const plan = await read('plans/' + detail.plan_id)
  expect(plan.proposed_purchase.supplier_id).toBe('B')
  await page.getByRole('button', { name: '核对 20 件采购', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('¥560')
  await expect(
    page.getByRole('button', { name: '确认采购 20 件 · ¥240', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: '返回修改', exact: true }).click()
  await page.getByRole('button', { name: '开启自动跟进', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止自动跟进', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '停止自动跟进', exact: true }).click()
  await expect(page.getByRole('button', { name: '开启自动跟进', exact: true })).toBeEnabled()
  await page.reload()
  await page.getByRole('button', { name: '供应异常应对', exact: true }).click()
  await expect(page.locator('.decision-card')).toContainText('¥240')
  await expect(page.getByLabel('本次应急预算（元）', { exact: true })).toHaveValue('300.00')
  expect(errors).toEqual([])
  if (process.env.RECOVERY_OUTPUT) {
    await page.screenshot({
      path: process.env.RECOVERY_OUTPUT + '/recovery-real-browser.png',
      fullPage: true,
    })
    await writeFile(
      process.env.RECOVERY_OUTPUT + '/recovery-real-browser.json',
      JSON.stringify(
        {
          status: 'passed',
          fixture: 'four-demand-days-no-original-order',
          checks: [
            'real_session_capability',
            'b20_prevents_20_lost_units',
            'budget_revision_200_wait',
            'pending_plan_supplier_binding',
            'confirmation_cash_560',
            'no_purchase_action',
            'followup_controls',
            'refresh_persistence',
          ],
          model_calls: 0,
          supplier_calls: 0,
          page_errors: errors,
        },
        null,
        2,
      ),
    )
  }
  console.log('PASS: 8 real browser/API/PostgreSQL checks; zero model and supplier calls')
} catch (error) {
  console.error('Browser page errors:', errors)
  console.error((await page.locator('body').innerText()).slice(0, 4000))
  if (process.env.RECOVERY_OUTPUT)
    await page.screenshot({
      path: process.env.RECOVERY_OUTPUT + '/recovery-browser-failed.png',
      fullPage: true,
    })
  throw error
} finally {
  await browser.close()
}
