import { test, expect, type Page } from '@playwright/test'

function gate() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

// Real business setup; all Agent requests below are controlled and use no model.
async function setup(page: Page, action: string) {
  if (process.env.ENVIRONMENT_TEST_TOKEN)
    await page.request.post('/api/session', { data: { token: process.env.ENVIRONMENT_TEST_TOKEN } })
  await page.route('**/api/session', async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response, json: { ...(await response.json()), agentEnabled: true } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: '联调控制 · 合成数据', exact: true }).click()
  await page.getByRole('button', { name: '创建新的 SC-01 场景', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: '开始备货跟进', exact: true }).click()
  await page.getByRole('button', { name: '按以上条件开始', exact: true }).click()
  await expect(page.getByRole('heading', { name: '建议补货 40 件', exact: true })).toBeVisible()
  const store = await page.evaluate(() => localStorage.getItem('ss.store')!)
  const missions = await (
    await page.request.get(`/api/backend/api/v1/missions?store_id=${store}&limit=100`)
  ).json()
  const original = missions.items.find((m: any) => m.status === 'ACTIVE')
  let switched = false
  const entered = gate(),
    delayed = gate()
  const mutations: string[] = []
  const conversation = (old: boolean) => ({
    id: old ? 'scope-old-conversation' : 'scope-new-conversation',
    is_default: true,
    active_run_id: old && action === 'cancel' ? 'scope-old-run' : null,
    followup_enabled: false,
    followup_version: 1,
  })
  await page.route(/\/api\/backend\/api\/v1\/missions\?/, (route) =>
    route.fulfill({
      json: {
        ...missions,
        items: [{ ...original, id: switched ? 'scope-new-mission' : original.id }],
      },
    }),
  )
  await page.route('**/api/backend/api/v1/missions/scope-new-mission/timeline?*', (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }),
  )
  await page.route(
    /\/api\/backend\/api\/v1\/missions\/[^/]+\/conversations(?:\?|$)/,
    async (route) => {
      if (route.request().method() === 'POST') {
        mutations.push('create')
        entered.release()
        await delayed.promise
        await route.fulfill({ json: conversation(true) })
      } else {
        const old = route
          .request()
          .url()
          .includes('/' + original.id + '/')
        await route.fulfill({
          json: {
            items: old && action === 'create' ? [] : [conversation(old)],
            next_cursor: null,
          },
        })
      }
    },
  )
  await page.route(
    /\/api\/backend\/api\/v1\/conversations\/scope-.*\/messages(?:\?|$)/,
    async (route) => {
      if (route.request().method() === 'POST') {
        mutations.push('send')
        entered.release()
        await delayed.promise
        await route.fulfill({ status: 202, json: { agent_run_id: 'scope-old-run' } })
      } else {
        const old = route.request().url().includes('/scope-old-conversation/')
        await route.fulfill({
          json: {
            items: [
              {
                id: old ? 'old-message' : 'new-message',
                seq: 1,
                role: 'assistant',
                run_id: null,
                content: old ? '旧任务会话' : '新任务会话',
                references: [],
              },
            ],
            next_after_seq: null,
          },
        })
      }
    },
  )
  await page.route('**/api/backend/api/v1/agent-runs/scope-old-run', (route) =>
    route.fulfill({
      json: {
        id: 'scope-old-run',
        status: 'WAITING_INPUT',
        question: '旧任务待补充',
        interrupt_id: 'old-interrupt',
      },
    }),
  )
  await page.route('**/api/backend/api/v1/agent-runs/scope-old-run/cancel', async (route) => {
    entered.release()
    await delayed.promise
    // An old failure must not become a warning in the new task.
    await route.fulfill({
      status: 409,
      json: { error: { code: 'OLD_SCOPE_ERROR', message: '旧任务取消失败' } },
    })
  })
  await page.route(
    '**/api/backend/api/v1/conversations/scope-old-conversation/followup',
    async (route) => {
      entered.release()
      await delayed.promise
      await route.fulfill({ json: { ...conversation(true), followup_enabled: true } })
    },
  )
  await page.goto('/?view=task')
  await expect(page.getByLabel('追问这项备货任务', { exact: true })).toBeEnabled()
  if (action !== 'create')
    await expect(page.getByRole('log', { name: '任务对话' })).toContainText('旧任务会话')
  return {
    entered,
    delayed,
    mutations,
    switchMission: async () => {
      switched = true
      await expect(page.getByRole('log', { name: '任务对话' })).toContainText('新任务会话')
    },
  }
}

for (const action of ['create', 'send', 'cancel', 'followup']) {
  test(`Agent scope: delayed ${action} cannot change the next mission`, async ({ page }) => {
    const scope = await setup(page, action)
    const response = page
      .waitForResponse(
        (r) =>
          ['POST', 'PATCH'].includes(r.request().method()) &&
          (action === 'create'
            ? /\/missions\/[^/]+\/conversations$/.test(r.url())
            : action === 'send'
              ? r.url().endsWith('/scope-old-conversation/messages')
              : action === 'cancel'
                ? r.url().endsWith('/scope-old-run/cancel')
                : r.url().endsWith('/scope-old-conversation/followup')),
      )
      .catch(() => null)
    try {
      if (action === 'create' || action === 'send') {
        await page.getByLabel('追问这项备货任务', { exact: true }).fill('只发送到旧任务')
        await page.getByRole('button', { name: '发送卡片内消息', exact: true }).click()
      } else if (action === 'cancel') {
        await expect(page.getByText('旧任务待补充', { exact: true })).toBeVisible()
        await page.getByRole('button', { name: '停止本轮回答', exact: true }).click()
      } else {
        await page.getByRole('button', { name: 'Agent主动解读：未开启', exact: true }).click()
      }
      await scope.entered.promise
      await scope.switchMission()
      const input = page.getByLabel('追问这项备货任务', { exact: true })
      await expect(input).toHaveValue('')
      await input.fill('新任务尚未发送的草稿')
      scope.delayed.release()
      const completed = await response
      expect(
        completed,
        'The delayed Agent request must receive its controlled response',
      ).not.toBeNull()
      await completed!.finished()
      await page.evaluate(
        () =>
          new Promise<void>((resolve) => {
            requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
          }),
      )
      await expect(input).toHaveValue('新任务尚未发送的草稿')
      await expect(input).toBeEnabled()
      await expect(page.getByText('旧任务待补充', { exact: true })).toHaveCount(0)
      await expect(page.getByText(/旧任务取消失败|OLD_SCOPE_ERROR/)).toHaveCount(0)
      await expect(
        page.getByRole('button', { name: 'Agent主动解读：未开启', exact: true }),
      ).toBeVisible()
      if (action === 'create') expect(scope.mutations).toEqual(['create'])
    } finally {
      scope.delayed.release()
    }
  })
}
