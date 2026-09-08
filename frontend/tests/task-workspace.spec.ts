import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
const original = JSON.parse(
  readFileSync(new URL('./fixtures/overview-pending.json', import.meta.url), 'utf8'),
)
const completedFixture = JSON.parse(
  readFileSync(new URL('./fixtures/overview.json', import.meta.url), 'utf8'),
)

// All /api traffic is intercepted: these exercise the actual Vue UI against
// controlled protocol states, without a model, simulator changes, or procurement.
async function setup(page: Page, running = true, initialQuantity?: number) {
  const f = structuredClone(original)
  f.catalog.products[0].name = '精品咖啡豆'
  f.missions.items[0].objective = '为周末活动备货，采购前确认并持续跟进到货。'
  f.plan.expires_at = '2099-01-01T00:00:00Z'
  if (initialQuantity !== undefined) {
    const candidate = f.plan.candidates.find((c: any) => c.quantity === initialQuantity)
    f.plan.proposed_purchase.quantity = initialQuantity
    f.plan.proposed_purchase.total_minor = candidate.spend_minor
  }
  const mission = f.missions.items[0],
    id = mission.id
  const references = [
    {
      type: 'document',
      id: 'doc-one',
      version_id: 'version-1',
      generation_id: 'generation-1',
      chunk_id: 'chunk-2',
      metadata_revision: 2,
      locator: { section: '供货说明' },
      content_sha256: 'example-hash',
    },
  ]
  const run: any = {
    id: 'run-current',
    conversation_id: 'conv-one',
    status: running ? 'RUNNING' : 'SUCCEEDED',
    input_through_seq: 3,
    trigger: 'USER',
    graph_version: 'test',
    interrupt_id: null,
    question: null,
    output: null,
    error_code: null,
    created_at: '2026-09-08T08:00:00Z',
    finished_at: null,
    tools: [{ tool: 'get_dashboard', invocation_id: 'read-1', ok: true, references: [] }],
  }
  const messages: any[] = [
    {
      id: 'm1',
      seq: 1,
      role: 'user',
      content: '解释当前备货方案',
      run_id: 'run-old',
      references: [],
      created_at: '2026-09-08T07:00:00Z',
    },
    {
      id: 'm2',
      seq: 2,
      role: 'assistant',
      content: '**建议补 40 件。**\n\n- 先核对现金与库存。\n- 每笔采购由你确认。',
      run_id: 'run-old',
      references,
      created_at: '2026-09-08T07:00:02Z',
    },
    {
      id: 'm3',
      seq: 3,
      role: 'user',
      content: '如果只补20件呢？先只试算。',
      run_id: 'run-current',
      references: [],
      created_at: '2026-09-08T08:00:00Z',
    },
  ]
  const control = {
    f,
    run,
    messages,
    writes: [] as { path: string; key: string | undefined; body: any }[],
    failRun: false,
    loseMessage: false,
    messageCount: 0,
    paginateConversations: false,
  }
  const conversation = () => ({
    id: 'conv-one',
    mission_id: id,
    store_id: 'overview-fixture-a',
    principal_id: 'test-owner',
    title: '活动备货',
    is_default: true,
    active_run_id: ['QUEUED', 'RUNNING', 'WAITING_INPUT'].includes(run.status) ? run.id : null,
    followup_enabled: false,
    followup_version: 1,
  })
  await page.route('**/api/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname.replace('/api/backend/api/v1/', '')
    if (url.pathname === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: 'test-owner',
          roles: ['admin'],
          agentEnabled: true,
          devTools: false,
          planRevision: true,
        },
      })
    if (request.method() !== 'GET') {
      const body = request.postDataJSON(),
        key = request.headers()['idempotency-key']
      control.writes.push({ path, key, body })
      if (path === 'conversations/conv-one/messages') {
        control.messageCount++
        if (control.loseMessage && control.messageCount === 1) return route.abort('connectionreset')
        messages.push({
          id: 'm-new',
          seq: messages.length + 1,
          role: 'user',
          content: body.content,
          run_id: run.id,
          references: [],
          created_at: new Date().toISOString(),
        })
        return route.fulfill({
          status: 202,
          json: { message_id: 'm-new', agent_run_id: run.id, conversation_id: 'conv-one' },
        })
      }
      if (path === `agent-runs/${run.id}/cancel`) {
        run.status = 'CANCELLED'
        return route.fulfill({ json: run })
      }
      if (path === `missions/${id}/control` && body.operation === 'complete') {
        mission.status = 'COMPLETED'
        mission.current_plan_id = null
        mission.schedule.enabled = false
        mission.schedule.next_run_at = null
        return route.fulfill({ json: mission })
      }
      return route.fulfill({
        status: 409,
        json: {
          error: { code: 'TEST_BLOCKED_WRITE', message: 'This fixture does not forward writes.' },
        },
      })
    }
    if (path === 'stores')
      return route.fulfill({
        json: {
          items: [
            {
              store_id: 'overview-fixture-a',
              currency: 'CNY',
              source_type: 'simulation',
              simulation_time: f.dashboard.state.simulation_time,
            },
          ],
          next_cursor: null,
          active_store: { store_id: 'overview-fixture-a' },
        },
      })
    if (path === `missions/${id}/conversations`) {
      if (control.paginateConversations && !url.searchParams.get('after'))
        return route.fulfill({
          json: {
            items: [{ ...conversation(), id: 'other-conversation', is_default: false }],
            next_cursor: 'first-page',
          },
        })
      return route.fulfill({ json: { items: [conversation()], next_cursor: null } })
    }
    if (path === 'conversations/conv-one/messages')
      return route.fulfill({
        json: {
          items: messages.filter((m) => m.seq > Number(url.searchParams.get('after_seq') || 0)),
          next_after_seq: null,
        },
      })
    if (path === 'agent-runs/run-old')
      return route.fulfill({
        json: {
          ...run,
          id: 'run-old',
          status: 'SUCCEEDED',
          input_through_seq: 1,
          tools: [{ tool: 'get_plan', invocation_id: 'old-plan', ok: true, references }],
        },
      })
    if (path === `agent-runs/${run.id}`) {
      if (control.failRun) return route.abort('connectionreset')
      return route.fulfill({ json: run })
    }
    if (path === `missions/${id}`) return route.fulfill({ json: mission })
    if (path === `missions/${id}/timeline`) return route.fulfill({ json: f.timeline })
    if (path === `missions/${id}/plans`)
      return route.fulfill({ json: { items: [f.plan], next_cursor: null } })
    if (path === `plans/${f.plan.id}`) return route.fulfill({ json: f.plan })
    if (f[path]) return route.fulfill({ json: f[path] })
    return route.fulfill({
      status: 404,
      json: { error: { code: 'TEST_MISSING_READ', message: path } },
    })
  })
  await page.goto('/')
  await expect(page.locator('.task-card')).toBeVisible()
  await page.getByRole('button', { name: '查看任务与方案', exact: true }).click()
  await expect(page.locator('.task-workspace')).toBeVisible()
  return control
}

test('同一任务跨首页/详情/刷新；草稿保留，工具按调用身份去重，历史不冒充当前过程', async ({
  page,
}, info) => {
  const c = await setup(page)
  const task = await page.locator('.task-workspace').getAttribute('data-task-id')
  await expect(page.locator('.agent-run-status')).toContainText('正在处理你的要求')
  await expect(page.locator('[data-invocation="read-1"]')).toBeVisible()
  expect(await page.locator('.agent-run-status').textContent()).not.toContain('正在核对现金')
  c.run.tools.push({ tool: 'get_dashboard', invocation_id: 'read-2', ok: true, references: [] })
  await expect(page.locator('[data-invocation]')).toHaveCount(2)
  await expect(page.locator('[data-invocation="read-2"]')).toBeVisible()
  await page.getByRole('button', { name: '停止本轮回答', exact: true }).click()
  const input = page.getByLabel('追问这项备货任务', { exact: true })
  await input.fill('还没有发送的任务草稿')
  await page.getByRole('button', { name: '返回今日', exact: true }).click()
  await expect(page.locator('.task-card')).toHaveAttribute('data-task-id', task!)
  await page.getByRole('button', { name: '查看Agent工作区', exact: true }).click()
  await expect(input).toHaveValue('还没有发送的任务草稿')
  await page.getByRole('button', { name: '查看本轮过程', exact: true }).click()
  await expect(page.locator('[data-invocation="old-plan"]')).toBeVisible()
  await expect(page.locator('[data-invocation="read-2"]')).toHaveCount(0)
  await page.getByRole('button', { name: '返回当前工作', exact: true }).click()
  await page.reload()
  await expect(page.locator('.task-workspace')).toHaveAttribute('data-task-id', task!)
  await expect(page.locator('.agent-run-status')).toContainText('本轮已停止')
  await expect(page.locator('.target-active')).toHaveCount(0)
  await page.screenshot({
    path: info.outputPath('task-desktop.jpg'),
    type: 'jpeg',
    quality: 80,
    fullPage: false,
  })
  expect(c.writes.map((w) => w.path)).toEqual(['agent-runs/run-current/cancel'])
})

test('富文本安全、中文输入法、发送丢响应沿用幂等键', async ({ page }) => {
  const c = await setup(page, false)
  c.messages.push({
    id: 'm4',
    seq: 4,
    role: 'assistant',
    content:
      '**已完成试算**\n\n<script>window.pwned=1</script>\n\n[危险](javascript:alert(1))\n\n| 数量 | 现金 |\n| --- | --- |\n| 20 | ¥800 |',
    run_id: c.run.id,
    references: [],
    created_at: new Date().toISOString(),
  })
  await expect(page.locator('.agent-markdown strong').last()).toHaveText('已完成试算')
  await expect(
    page.locator('.agent-markdown script,.agent-markdown a[href^="javascript:"]'),
  ).toHaveCount(0)
  const input = page.getByLabel('追问这项备货任务', { exact: true })
  await input.fill('只查询，不采购')
  await input.dispatchEvent('keydown', {
    key: 'Enter',
    code: 'Enter',
    isComposing: true,
    keyCode: 229,
  })
  expect(c.writes).toHaveLength(0)
  c.loseMessage = true
  await page.getByRole('button', { name: '发送卡片内消息', exact: true }).click()
  await expect(page.getByRole('button', { name: '查询或重试原消息', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查询或重试原消息', exact: true }).click()
  await expect(input).toHaveValue('')
  expect(c.writes).toHaveLength(2)
  expect(c.writes[0]!.key).toBeTruthy()
  expect(c.writes[0]!.key).toBe(c.writes[1]!.key)
  await expect(page.locator('.pending-message')).toHaveCount(0)
})

test('运行连接丢失停止忙碌动效；恢复后终态不掩盖失败子步骤', async ({ page }) => {
  const c = await setup(page)
  c.failRun = true
  await expect(page.locator('.agent-run-status')).toContainText('连接中断')
  await expect(page.locator('.agent-run-status')).not.toHaveClass(/is-running/)
  c.failRun = false
  c.run.status = 'SUCCEEDED'
  c.run.tools.push({
    tool: 'search_documents',
    invocation_id: 'search-failed',
    ok: false,
    references: [],
  })
  await page.getByRole('button', { name: '重新同步', exact: true }).click()
  await expect(page.locator('.agent-run-status')).toContainText('本轮工作已完成')
  await expect(page.locator('.tool-error-count')).toContainText('1 步未成功')
  await expect(page.locator('.task-workspace .task-heading-actions')).toContainText('等待你确认')
  expect(c.writes).toHaveLength(0)
})

test('结束委托绑定原任务，刷新可回看；未知采购阻止结束', async ({ page }) => {
  const c = await setup(page, false)
  const a = structuredClone(completedFixture.actions.items[0])
  a.mission_id = c.f.missions.items[0].id
  a.status = 'UNKNOWN'
  c.f.actions.items = [a]
  c.f.missions.items[0].current_action_id = a.id
  await expect(page.getByRole('heading', { name: '采购结果还没有核实', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '结束这项委托', exact: true })).toBeDisabled()
  c.f.actions.items = []
  c.f.missions.items[0].current_action_id = null
  await expect(page.getByRole('button', { name: '结束这项委托', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '结束这项委托', exact: true }).click()
  await page.getByRole('button', { name: '确认结束委托', exact: true }).click()
  await expect(page.getByRole('heading', { name: '这项委托已完成', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '这项委托已完成', exact: true })).toBeVisible()
  expect(c.writes).toHaveLength(1)
  expect(c.writes[0]!.body.operation).toBe('complete')
})

test('手机任务工作区、长表格不溢出，减少动效生效', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 390, height: 844 })
  const c = await setup(page)
  await page.getByRole('button', { name: 'Agent 工作', exact: true }).click()
  c.messages.push({
    id: 'long',
    seq: 4,
    role: 'assistant',
    content:
      '| 方案 | 现金 | 来源与说明 | 到货 |\n| --- | --- | --- | --- |\n| 20件 | ¥800 | 需要核对的长来源说明'.repeat(
        1,
      ) + ' | 下周 |',
    run_id: c.run.id,
    references: [],
    created_at: new Date().toISOString(),
  })
  await expect(page.locator('.agent-markdown table')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  const animations = await page
    .locator('.agent-live-dot')
    .evaluateAll((nodes) => nodes.map((n) => getComputedStyle(n).animationName))
  expect(
    animations.every((n) => n === 'none'),
    JSON.stringify({
      animations,
      reduced: await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches),
    }),
  ).toBe(true)
  await page.getByRole('button', { name: '返回今日', exact: true }).click()
  await expect(page.getByRole('button', { name: '移动端Agent工作区', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '移动端Agent工作区', exact: true }).click()
  await expect(page.locator('.task-workspace')).toHaveAttribute('data-mobile-panel', 'agent')
  await expect(page.getByRole('complementary', { name: 'Agent工作区' })).toBeVisible()
  await page.screenshot({
    path: info.outputPath('task-mobile.jpg'),
    type: 'jpeg',
    quality: 80,
    fullPage: false,
  })
  expect(c.writes).toHaveLength(0)
})

test('事实更新先等待新方案；修订回执来自真实版本，现金不因方案调整改变', async ({ page }, info) => {
  const c = await setup(page, false, 40)
  await expect(page.getByRole('button', { name: '核对 40 件采购', exact: true })).toBeVisible()
  c.f.dashboard.state.state_version++
  await expect(
    page.getByRole('heading', { name: '经营情况已变化，方案待更新', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '核对 40 件采购', exact: true })).toHaveCount(0)
  c.run.id = 'run-revision'
  c.run.input_through_seq = 4
  c.run.status = 'RUNNING'
  c.run.created_at = '2026-09-08T08:01:00Z'
  c.messages.push({
    id: 'm-revision',
    seq: 4,
    role: 'user',
    content: '把这轮上限改成20件，采购前让我确认。',
    run_id: 'run-revision',
    references: [],
    created_at: '2026-09-08T08:01:00Z',
  })
  await expect(page.locator('.agent-run-status')).toContainText('正在处理你的要求')
  const revised = structuredClone(c.f.plan)
  revised.id = 'revised-plan'
  revised.plan_version++
  revised.state_version = c.f.dashboard.state.state_version
  revised.input_snapshot.state.state_version = revised.state_version
  revised.proposed_purchase.quantity = 20
  revised.proposed_purchase.total_minor = 20000
  c.f.plan = revised
  c.f.missions.items[0].current_plan_id = revised.id
  await expect(page.getByRole('button', { name: '核对 20 件采购', exact: true })).toBeVisible()
  await expect(page.locator('.plan-change-receipt')).toContainText(/40\s*→\s*20/)
  await expect(page.getByTestId('cash')).toHaveText('¥1,000')
  await expect(page.getByTestId('inbound')).toHaveText('0')
  c.run.tools.push({
    tool: 'evaluate_plan',
    invocation_id: 'calculation-1',
    ok: true,
    references: [],
  })
  c.run.tools.push({ tool: 'revise_plan', invocation_id: 'revision-1', ok: true, references: [] })
  await expect(page.locator('[data-invocation="revision-1"]')).toBeVisible()
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.screenshot({
    path: info.outputPath('task-working-desktop.jpg'),
    type: 'jpeg',
    quality: 85,
    fullPage: false,
  })
  expect(c.writes).toHaveLength(0)
})

test('会话分页使用后端after游标，第二页默认会话不会被第一条替代', async ({ page }) => {
  const c = await setup(page)
  c.paginateConversations = true
  await page.reload()
  await expect(page.getByRole('log', { name: '任务对话' })).toContainText('解释当前备货方案')
  await expect(page.locator('.agent-run-status')).toContainText('正在处理你的要求')
  expect(c.writes).toHaveLength(0)
})
