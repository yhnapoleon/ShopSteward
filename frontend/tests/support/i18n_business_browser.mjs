import { chromium, expect } from '@playwright/test'
import { writeFile } from 'node:fs/promises'
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
  writes = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('request', (r) => {
  if (r.method() !== 'GET') writes.push({ path: new URL(r.url()).pathname, method: r.method() })
})
async function get(path) {
  const r = await page.request.get(base + '/api/backend/api/v1/' + path)
  expect(r.ok(), await r.text()).toBe(true)
  return r.json()
}
async function state() {
  return (await get('dashboard?store_id=' + store)).state
}
async function settings() {
  await page.locator('.settings-entry:visible, .mobile-settings-entry:visible').first().click()
  return page.locator('dialog[open]')
}
try {
  expect(
    (
      await page.request.post(base + '/api/session', { data: { token: process.env.WORK_AUTH } })
    ).ok(),
  ).toBe(true)
  const originalMission = (await get('missions?store_id=' + store)).items[0]
  await page.goto(base + '/?view=task&mission=' + originalMission.id + '&store=' + store)
  await expect(page.locator('.task-workspace')).toBeVisible()
  const before = await state()
  let dialog = await settings()
  await dialog.getByRole('radio', { name: /English/ }).check()
  await dialog.getByLabel('Business check interval', { exact: true }).selectOption('60')
  await expect(dialog.getByRole('status')).toContainText('Saved automatically')
  let mission = (await get('missions?store_id=' + store)).items[0]
  expect(mission.schedule.interval_seconds).toBe(60)
  const version = mission.schedule.version
  await dialog.getByLabel('Business check interval', { exact: true }).selectOption('15')
  await expect(dialog.getByRole('status')).toContainText('Saved automatically')
  mission = (await get('missions?store_id=' + store)).items[0]
  expect(mission.schedule.interval_seconds).toBe(15)
  expect(mission.schedule.version).toBe(version + 1)
  await dialog.getByRole('button', { name: 'Close dialog' }).click()
  expect(await state()).toEqual(before)
  expect((await get('actions?store_id=' + store)).items).toHaveLength(0)
  await expect(
    page.getByRole('button', { name: 'Review 40-unit purchase', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Review 40-unit purchase', exact: true }).click()
  dialog = page.locator('dialog[open]')
  await expect(dialog).toContainText('CNY')
  expect((await get('actions?store_id=' + store)).items).toHaveLength(0)
  await dialog.getByRole('button', { name: /Confirm 40 units/ }).dblclick()
  await expect.poll(async () => (await state()).cash_minor).toBe(60000)
  const accepted = await state(),
    actions = (await get('actions?store_id=' + store)).items
  expect(actions).toHaveLength(1)
  expect(actions[0].quantity).toBe(40)
  expect(actions[0].status).toBe('SUCCEEDED')
  expect(accepted.available_cash_minor).toBe(60000)
  expect(accepted.reserved_cash_minor).toBe(0)
  expect(accepted.stocks[0].on_hand).toBe(20)
  expect(accepted.stocks[0].in_transit).toBe(40)
  dialog = await settings()
  await dialog.getByRole('radio', { name: /简体中文/ }).check()
  await dialog.getByRole('button', { name: '关闭对话框' }).click()
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
  expect(await state()).toEqual(accepted)
  expect((await get('actions?store_id=' + store)).items).toHaveLength(1)
  dialog = await settings()
  await dialog.getByRole('button', { name: '暂停主动跟进', exact: true }).click()
  await page.getByRole('button', { name: '确认暂停主动跟进', exact: true }).click()
  dialog = await settings()
  await dialog.getByLabel('业务检查间隔', { exact: true }).selectOption('300')
  await expect(dialog.getByRole('status')).toContainText('已自动保存')
  mission = (await get('missions?store_id=' + store)).items[0]
  expect(mission.status).toBe('PAUSED')
  expect(mission.schedule.next_run_at).toBeNull()
  expect(mission.schedule.interval_seconds).toBe(300)
  expect(await state()).toEqual(accepted)
  await dialog.getByRole('radio', { name: /English/ }).check()
  await dialog.getByRole('button', { name: 'Close dialog' }).click()
  await page.screenshot({
    path: output + '/approved-english.png',
    fullPage: true,
    animations: 'disabled',
  })
  expect(errors).toEqual([])
  await writeFile(
    output + '/checks.json',
    JSON.stringify(
      {
        before,
        accepted,
        missionStatus: mission.status,
        schedule: mission.schedule,
        actions: actions.map((a) => ({ id: a.id, quantity: a.quantity, status: a.status })),
        pageErrors: errors,
        writes,
        realHTTP: true,
        realPostgreSQL: true,
        supplier: 'deterministic test adapter',
        modelCalls: 0,
      },
      null,
      2,
    ),
  )
  console.log(
    'PASS: language invariance, real autosave versions, explicit approval only, one purchase, exact cash/stock, pause preserved',
  )
} catch (error) {
  await page.screenshot({ path: output + '/failure.png', fullPage: true })
  await writeFile(output + '/failure.txt', await page.locator('body').innerText())
  throw error
} finally {
  await browser.close()
}
