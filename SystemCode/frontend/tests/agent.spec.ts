import { test, expect, type Page } from '@playwright/test'

test.skip(process.env.AGENT_E2E !== 'true', 'Opt in to real model usage with AGENT_E2E=true')

async function setup(page: Page) {
  await page.goto('/')
  expect((await (await page.request.get('/api/session')).json()).agentEnabled).toBe(true)
  await page.getByRole('button', { name: '联调控制 · 合成数据', exact: true }).click()
  await page.getByRole('button', { name: '创建新的 SC-01 场景', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: '开始备货跟进', exact: true }).click()
  await page.getByRole('button', { name: '按以上条件开始', exact: true }).click()
  await expect(page.getByRole('heading', { name: '建议补货 40 件', exact: true })).toBeVisible()
  return await page.evaluate(() => localStorage.getItem('ss.store')!)
}

async function send(page: Page, content: string, resume = false) {
  await page.getByLabel('追问这项备货任务', { exact: true }).fill(content)
  const accepted = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      (resume ? r.url().endsWith('/resume') : /\/conversations\/[^/]+\/messages$/.test(r.url())),
  )
  await page.getByRole('button', { name: '发送卡片内消息', exact: true }).click()
  const response = await accepted
  expect(response.status()).toBe(202)
  return (await response.json()).agent_run_id as string
}

async function finished(page: Page, id: string, status = 'SUCCEEDED') {
  let run: any
  await expect
    .poll(
      async () => {
        run = await (await page.request.get('/api/backend/api/v1/agent-runs/' + id)).json()
        return ['FAILED', 'CANCELLED', 'WAITING_INPUT', 'SUCCEEDED'].includes(run.status)
      },
      { timeout: 110000, intervals: [1000, 2000] },
    )
    .toBe(true)
  expect(run.status, JSON.stringify(run)).toBe(status)
  return run
}

async function storeData(page: Page, store: string) {
  const prefix = '/api/backend/api/v1/'
  const [dashboard, actions, missions] = await Promise.all(
    ['dashboard', 'actions', 'missions'].map(async (resource) =>
      (await page.request.get(`${prefix}${resource}?store_id=${store}`)).json(),
    ),
  )
  return { dashboard, actions: actions.items, mission: missions.items[0] }
}

test('真实Luna：解释、只读试算、明确修订、用户审批与刷新持久化', async ({ page }, info) => {
  test.setTimeout(360000)
  const store = await setup(page)
  const initial = await storeData(page, store)
  const explanation = await finished(
    page,
    await send(page, '解释当前方案为什么推荐这个数量，请读取当前方案。'),
  )
  expect(explanation.output.model).toBe('gpt-5.6-luna')
  expect(explanation.tools.some((t: any) => t.tool === 'get_plan')).toBe(true)
  await expect(page.getByRole('log', { name: '任务对话' })).toContainText(
    explanation.output.content,
  )
  const whatIf = await finished(
    page,
    await send(page, '如果本次最多买20件，会怎么样？只调用evaluate_plan试算，不修改本轮方案。'),
  )
  expect(whatIf.tools.some((t: any) => t.tool === 'evaluate_plan')).toBe(true)
  const unchanged = await storeData(page, store)
  expect(unchanged.mission.current_plan_id).toBe(initial.mission.current_plan_id)
  expect(unchanged.actions).toHaveLength(0)
  expect(unchanged.dashboard.state).toEqual(initial.dashboard.state)
  const revised = await finished(
    page,
    await send(
      page,
      '明确修改这一次方案：本轮最多采购20件。请调用revise_plan生成待确认方案，不能执行采购。',
    ),
  )
  expect(revised.tools.some((t: any) => t.tool === 'revise_plan' && t.ok)).toBe(true)
  await expect(page.getByRole('button', { name: '核对 20 件采购', exact: true })).toBeVisible()
  expect((await storeData(page, store)).actions).toHaveLength(0)
  await page.getByRole('button', { name: '核对 20 件采购', exact: true }).click()
  await page.getByRole('button', { name: '确认采购 20 件 · ¥200', exact: true }).click()
  await expect(page.getByTestId('cash')).toHaveText('¥800')
  await expect(page.getByTestId('inbound')).toHaveText('20')
  await page.reload()
  await expect(page.getByTestId('cash')).toHaveText('¥800')
  await expect(page.getByRole('log', { name: '任务对话' })).toContainText(revised.output.content)
  const final = await storeData(page, store)
  expect(final.actions).toHaveLength(1)
  await info.attach('real-agent-business', {
    body: JSON.stringify({ store, explanation, whatIf, revised, final }),
    contentType: 'application/json',
  })
})

test('真实Luna：澄清刷新后恢复、持久偏好、取消与后续发送', async ({ page }, info) => {
  test.setTimeout(360000)
  const store = await setup(page)
  const id = await send(
    page,
    '我要保存一个长期偏好，但尚未决定具体内容。请调用clarify先问我希望保存什么，不要自行保存。',
  )
  const waiting = await finished(page, id, 'WAITING_INPUT')
  await page.reload()
  await expect(page.getByText(waiting.question, { exact: true })).toBeVisible()
  const resumed = await send(
    page,
    '请长期记住：回答时先给一句结论，再给依据。保存为通用USER偏好。',
    true,
  )
  expect(resumed).toBe(id)
  const saved = await finished(page, resumed)
  expect(saved.tools.some((t: any) => t.tool === 'memory_edit' && t.ok)).toBe(true)
  const knowledge = await (
    await page.request.get(`/api/backend/api/v1/stores/${store}/agent-knowledge`)
  ).json()
  expect(knowledge.items.some((k: any) => k.kind === 'USER' && k.entries.length)).toBe(true)
  await expect(page.getByRole('log', { name: '任务对话' })).toContainText(saved.output.content)
  const cancelId = await send(page, '请调用clarify询问我下一步需要查看什么。')
  await finished(page, cancelId, 'WAITING_INPUT')
  // WAITING_INPUT must offer cancellation in the same UI as other active states.
  await page.getByRole('button', { name: '停止本轮回答', exact: true }).click()
  await finished(page, cancelId, 'CANCELLED')
  await expect(page.getByLabel('追问这项备货任务', { exact: true })).toBeEnabled()
  const next = await finished(
    page,
    await send(page, '我刚才保存的通用回答偏好是什么？仅查看，不修改。'),
  )
  expect(next.tools.some((t: any) => t.tool === 'memory_edit')).toBe(false)
  await info.attach('real-agent-memory-resume', {
    body: JSON.stringify({ store, waiting, saved, knowledge, next }),
    contentType: 'application/json',
  })
})

test('真实Luna：开启主动解读后经营事件产生持久跟进回复', async ({ page }, info) => {
  test.setTimeout(240000)
  const store = await setup(page)
  await finished(page, await send(page, '读取当前方案，简短解释。'))
  await page.getByRole('button', { name: 'Agent主动解读：未开启', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Agent主动解读：已开启', exact: true }),
  ).toBeVisible()
  const data = await storeData(page, store)
  const conversations = await (
    await page.request.get(`/api/backend/api/v1/missions/${data.mission.id}/conversations`)
  ).json()
  const conversation = conversations.items[0]
  // Set the supported minimum period through the real API to bound this acceptance run.
  const configured = await page.request.patch(
    `/api/backend/api/v1/conversations/${conversation.id}/followup`,
    {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      data: {
        enabled: true,
        interval_seconds: 60,
        expected_version: conversation.followup_version,
      },
    },
  )
  expect(configured.ok()).toBe(true)
  await page.getByRole('button', { name: '核对 40 件采购', exact: true }).click()
  await page.getByRole('button', { name: '确认采购 40 件 · ¥400', exact: true }).click()
  await expect(page.getByTestId('cash')).toHaveText('¥600')
  let followup: any
  await expect
    .poll(
      async () => {
        const messages = await (
          await page.request.get(
            `/api/backend/api/v1/conversations/${conversation.id}/messages?limit=100`,
          )
        ).json()
        for (const m of messages.items.filter((m: any) => m.role === 'assistant' && m.run_id)) {
          const run = await (
            await page.request.get('/api/backend/api/v1/agent-runs/' + m.run_id)
          ).json()
          if (run.trigger === 'FOLLOWUP' && run.status === 'SUCCEEDED') {
            followup = run
            return true
          }
        }
        return false
      },
      { timeout: 150000, intervals: [2000, 4000] },
    )
    .toBe(true)
  await expect(page.getByRole('log', { name: '任务对话' })).toContainText(followup.output.content)
  await page.getByRole('button', { name: 'Agent主动解读：已开启', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Agent主动解读：未开启', exact: true }),
  ).toBeVisible()
  await info.attach('real-agent-followup', {
    body: JSON.stringify({ store, followup }),
    contentType: 'application/json',
  })
})
