import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'
import { setup } from './support/i18n-fixture'
import { locale, t } from '../app/i18n'
import { localizedSamples, processQuotes, quoteCSV } from '../app/utils/quotations'
import { resultFile } from '../app/utils/workResultExport'

const storageKey = 'shopsteward.locale.v1'
const openSettings = async (page: import('@playwright/test').Page) => {
  await page.locator('.settings-entry:visible, .mobile-settings-entry:visible').first().click()
  const dialog = page.locator('dialog[open]')
  await expect(dialog).toHaveCSS('opacity', '1')
  return dialog
}
test('language switches immediately without writes, survives reload and syncs across tabs', async ({
  page,
  context,
}) => {
  const c = await setup(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '今天的经营安排。' })).toBeVisible()
  const dialog = await openSettings(page)
  await dialog.getByRole('radio', { name: /English/ }).check()
  await expect(dialog.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(dialog.getByRole('button', { name: /save/i })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: "Today's business, in view." })).toBeVisible()
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBe('en')
  await page.screenshot({ path: '../var/i18n/settings-desktop.png', fullPage: false })
  await page.reload()
  await expect(page.getByRole('heading', { name: "Today's business, in view." })).toBeVisible()
  const other = await context.newPage()
  await setup(other)
  await other.goto('/')
  await (await openSettings(other)).getByRole('radio', { name: /简体中文/ }).check()
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
  await expect(page.getByRole('heading', { name: '今天的经营安排。' })).toBeVisible()
  expect(c.writes).toEqual([])
  await other.close()
})

test('schedule change saves once, keeps enabled state and rolls back after failure', async ({
  page,
}) => {
  await setup(page)
  const writes: any[] = []
  let seconds = 30,
    version = 1,
    failed = false
  const fixture = JSON.parse(
    readFileSync(new URL('./fixtures/overview.json', import.meta.url), 'utf8'),
  )
  await page.route('**/api/backend/api/v1/missions**', async (route) => {
    if (route.request().url().includes('/schedule')) {
      const body = route.request().postDataJSON()
      writes.push(body)
      if (failed)
        return route.fulfill({ status: 409, json: { error: { code: 'STATE_VERSION_CONFLICT' } } })
      seconds = body.interval_seconds
      version++
      return route.fulfill({
        json: {
          ...fixture.missions.items[0].schedule,
          mission_id: fixture.missions.items[0].id,
          interval_seconds: seconds,
          version,
          enabled: false,
        },
      })
    }
    if (route.request().url().includes('?')) {
      const value = structuredClone(fixture.missions)
      Object.assign(value.items[0].schedule, { interval_seconds: seconds, version, enabled: false })
      return route.fulfill({ json: value })
    }
    const item = structuredClone(fixture.missions.items[0])
    Object.assign(item.schedule, { interval_seconds: seconds, version, enabled: false })
    return route.fulfill({ json: item })
  })
  await page.goto('/')
  const dialog = await openSettings(page)
  await dialog.getByLabel('业务检查间隔', { exact: true }).selectOption('60')
  await expect(dialog.getByRole('status')).toContainText('已自动保存')
  expect(writes).toEqual([{ interval_seconds: 60, enabled: false, expected_schedule_version: 1 }])
  failed = true
  await dialog.getByLabel('业务检查间隔', { exact: true }).selectOption('300')
  await expect(dialog.getByLabel('业务检查间隔', { exact: true })).toHaveValue('60')
  await expect(dialog).toContainText('经营状态已变化')
  expect(writes).toHaveLength(2)
})

test('English navigation, charts, mobile settings and quote flow remain usable', async ({
  page,
}) => {
  const c = await setup(page)
  await page.addInitScript((key) => localStorage.setItem(key, 'en'), storageKey)
  await page.goto('/?view=overview')
  await expect(page.getByTestId('overview-cash')).toContainText('CNY')
  await expect(page.locator('.overview-chart--sales svg')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible()
  await page.screenshot({ path: '../var/i18n/overview-desktop.png', fullPage: true })
  const dialog = await openSettings(page)
  await dialog.getByRole('button', { name: 'Close dialog' }).click()
  await page.getByRole('button', { name: 'Back to Today', exact: true }).click()
  await page.getByRole('button', { name: 'Organize a supplier quote' }).click()
  await page.getByRole('button', { name: 'Try sample quote A', exact: true }).click()
  await page.getByRole('button', { name: 'Organize quotes', exact: true }).click()
  await expect(page.locator('dialog[open]')).toContainText('Sample A')
  await expect(page.locator('dialog[open]')).toContainText('CNY')
  await page.getByRole('button', { name: 'Close dialog' }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  const mobile = await openSettings(page)
  await expect(mobile.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible()
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390)
  await page.screenshot({ path: '../var/i18n/settings-mobile.png', fullPage: false })
  expect(c.writes).toEqual([])
})

test('storage failures remain usable and never claim persistence', async ({ page }) => {
  await setup(page)
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException('Blocked', 'SecurityError')
    }
  })
  await page.goto('/')
  const dialog = await openSettings(page)
  await dialog.getByRole('radio', { name: /English/ }).check()
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(dialog.getByRole('alert')).toContainText('browser storage is unavailable')
})

test('English quote round trip, source preservation, system messages and raw JSON', () => {
  locale.value = 'en'
  try {
    const sample = localizedSamples()[0]!
    const result = processQuotes(sample.name, sample.text, null)
    expect(result.rows[0]?.unitPrice).toBe(10)
    expect(result.rows[0]?.moqPieces).toBe(24)
    expect(quoteCSV(result)).toContain('Unit price (CNY)')
    expect(t('本委托还有20件在途，到货后更新。')).toBe(
      '20 units remain in transit for this task. Updated after arrival.',
    )
    const value: any = {
      result: {
        kind: 'analysis',
        title: '用户的标题',
        content: '用户的原始内容',
        columns: ['原始字段'],
        rows: [['原始值']],
        provenance: { result_id: 'r1', result_version: 1, currency: 'CNY' },
      },
      is_latest_result: true,
    }
    const csv = resultFile(value, 'csv')
    expect(csv.text).toContain('Result ID')
    expect(csv.text).toContain('用户的原始内容')
    expect(csv.text).toContain('原始字段')
    expect(JSON.parse(resultFile(value, 'json').text)).toEqual(value)
    expect(csv.name).toBe('work-result-r1-v1.csv')
  } finally {
    locale.value = 'zh-CN'
  }
})

test('English chrome covers every primary view and task workspace', async ({ page }) => {
  await setup(page)
  await page.addInitScript((key) => localStorage.setItem(key, 'en'), storageKey)
  const fixture = JSON.parse(
    readFileSync(new URL('./fixtures/overview.json', import.meta.url), 'utf8'),
  )
  for (const view of ['today', 'following', 'journal', 'overview', 'documents', 'task']) {
    await page.goto(
      '/?view=' + view + (view === 'task' ? '&mission=' + fixture.missions.items[0].id : ''),
    )
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
    await expect(page.locator('.settings-entry')).toBeVisible()
    await expect(page.locator('body')).not.toContainText('正在读取经营数据…')
    // Source records and user-authored content are explicitly outside UI translation.
    const text = (await page.locator('body').innerText()).replaceAll(
      fixture.missions.items[0].objective,
      '',
    )
    const untranslated = text.split('\n').filter((line) => /[\u3400-\u9fff]/.test(line))
    expect(untranslated, view + ' must have no untranslated UI text').toEqual([])
  }
})

test('a lost schedule response plus failed verification never claims rollback or allows another write', async ({
  page,
}) => {
  await setup(page)
  const fixture = JSON.parse(
    readFileSync(new URL('./fixtures/overview.json', import.meta.url), 'utf8'),
  )
  const mission = fixture.missions.items[0]
  let applied = false,
    allowRead = false,
    writes = 0
  await page.route('**/api/backend/api/v1/missions**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/schedule')) {
      writes++
      applied = true
      return route.abort('connectionreset')
    }
    if (url.pathname.endsWith('/' + mission.id)) {
      if (!allowRead) return route.abort('connectionreset')
      const saved = structuredClone(mission)
      Object.assign(saved.schedule, { interval_seconds: 60, version: mission.schedule.version + 1 })
      return route.fulfill({ json: saved })
    }
    if (applied && url.pathname.endsWith('/missions')) return route.abort('connectionreset')
    return route.fallback()
  })
  await page.goto('/')
  const dialog = await openSettings(page)
  await dialog.getByLabel('业务检查间隔', { exact: true }).selectOption('60')
  await expect(dialog.getByRole('status')).toContainText('保存结果尚未核实')
  await expect(dialog.getByLabel('业务检查间隔', { exact: true })).toBeDisabled()
  await expect(dialog).not.toContainText('已自动保存')
  allowRead = true
  await dialog.getByRole('button', { name: '重新核对安排' }).click()
  await expect(dialog.getByLabel('业务检查间隔', { exact: true })).toHaveValue('60')
  await expect(dialog.getByLabel('业务检查间隔', { exact: true })).toBeEnabled()
  expect(writes).toBe(1)
})

test('language switches preserve original product names and task objectives', async ({ page }) => {
  await setup(page)
  const fixture = JSON.parse(
    readFileSync(new URL('./fixtures/overview.json', import.meta.url), 'utf8'),
  )
  fixture.catalog.products[0].name = '库存'
  await page.route('**/api/backend/api/v1/catalog?**', (route) =>
    route.fulfill({ json: fixture.catalog }),
  )
  await page.goto('/?view=task&mission=' + fixture.missions.items[0].id)
  await expect(page.getByRole('heading', { name: '库存', exact: true, level: 1 })).toBeVisible()
  const dialog = await openSettings(page)
  await dialog.getByRole('radio', { name: /English/ }).check()
  await dialog.getByRole('button', { name: 'Close dialog' }).click()
  await expect(page.getByRole('heading', { name: '库存', exact: true, level: 1 })).toBeVisible()
  await expect(page.locator('.task-workspace')).toContainText(fixture.missions.items[0].objective)
})
