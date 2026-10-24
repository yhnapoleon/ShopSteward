import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

async function setup(page: Page, role = 'operator') {
  const f = JSON.parse(
    readFileSync(new URL('./fixtures/overview-pending.json', import.meta.url), 'utf8'),
  )
  const store = f.missions.items[0].store_id
  const state = {
    lose: false,
    writes: [] as { path: string; key: string | undefined; body: any }[],
    view: {
      enabled: true,
      policy: { version: 0, mode: 'off', enabled_at: null },
      progress: {
        eligible_episodes: 3,
        first_checkpoint: 10,
        categories: { replenishment: 3 },
        source_domain: 'simulation',
        quality_calibrated: false,
      },
      assets: [
        {
          id: 'skill-1',
          version: 1,
          active_revision: null,
          kind: 'SKILL',
          task_family: 'replenishment',
          revisions: [
            {
              revision: 1,
              status: 'DRAFT',
              evidence_ids: ['source'],
              evaluation_id: null,
              quality: null,
              quality_decision: null,
              spec: {
                title: '比较补货方案',
                summary: '先读取，再比较',
                procedure: ['读取当前方案'],
                exceptions: ['缺少依据时询问'],
              },
            },
          ],
        },
      ],
    },
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url())
    const path = url.pathname.replace('/api/backend/api/v1/', '')
    if (url.pathname === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: 'owner',
          roles: [role],
          agentEnabled: false,
          devTools: false,
          workIntake: false,
        },
      })
    if (path.endsWith('/learning') && request.method() === 'GET')
      return route.fulfill({ json: state.view })
    if (request.method() !== 'GET') {
      state.writes.push({
        path,
        key: request.headers()['idempotency-key'],
        body: request.postDataJSON(),
      })
      if (path.endsWith('/learning/policy')) {
        state.view.policy.mode = request.postDataJSON().mode
        state.view.policy.version = 1
        if (state.lose) {
          state.lose = false
          return route.abort('failed')
        }
        return route.fulfill({ json: state.view.policy })
      }
      if (path.endsWith('/learning/forget')) {
        state.view.assets[0]!.revisions[0]!.status = 'REVOKED'
        return route.fulfill({ json: { status: 'REVOKED' } })
      }
      return route.fulfill({
        status: 409,
        json: { error: { code: 'LEARNING_QUALITY_REQUIRED', message: '质量证据不足' } },
      })
    }
    if (path === 'stores')
      return route.fulfill({
        json: {
          items: [{ store_id: store, currency: 'CNY', source_type: 'simulation' }],
          active_store: { store_id: store },
          next_cursor: null,
        },
      })
    if (f[path]) return route.fulfill({ json: f[path] })
    return route.fulfill({
      status: 404,
      json: { error: { code: 'RESOURCE_NOT_FOUND', message: path } },
    })
  })
  await page.goto('/?view=learning&store=' + store)
  await expect(page.getByRole('heading', { name: '学习与经验' })).toBeVisible()
  return state
}

test('未知质量不能启用，遗忘需要明确选择且不会采购', async ({ page }) => {
  const state = await setup(page)
  await expect(page.getByRole('button', { name: '启用此版本' })).toBeDisabled()
  await expect(page.getByText('质量检验 · 尚未验证')).toBeVisible()
  await page.getByLabel('学习方式').selectOption('suggest')
  await expect(page.getByLabel('学习方式')).toHaveValue('suggest')
  await page.getByRole('button', { name: '忘记这项经验' }).click()
  await page.getByRole('button', { name: '确认忘记', exact: true }).click()
  await expect(page.locator('summary')).toContainText('已忘记')
  expect(state.writes.map((w) => w.path.split('/').at(-1))).toEqual(['policy', 'forget'])
})

test('学习设置丢失响应后重试相同幂等键', async ({ page }) => {
  const state = await setup(page)
  state.lose = true
  await page.getByLabel('学习方式').selectOption('suggest')
  await expect(page.getByRole('button', { name: '核实并重试' })).toBeVisible()
  await page.getByRole('button', { name: '核实并重试' }).click()
  await expect(page.getByRole('button', { name: '核实并重试' })).toBeHidden()
  expect(state.writes).toHaveLength(2)
  expect(state.writes[0]!.key).toBe(state.writes[1]!.key)
  expect(state.writes[0]!.body).toEqual(state.writes[1]!.body)
})

test('只读用户无法改变学习设置', async ({ page }) => {
  const state = await setup(page, 'viewer')
  await expect(page.getByLabel('学习方式')).toBeDisabled()
  await expect(page.getByRole('button', { name: '忘记这项经验' })).toBeDisabled()
  expect(state.writes).toHaveLength(0)
})
