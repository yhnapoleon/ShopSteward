import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

// Real Vue UI with intercepted transport. No purchase is sent to a supplier. The owner reaches
// the mission either from the work page (`?view=work`, the normal entry) or from the older task
// page (`?view=task`), which stays reachable by link.
type Options = {
  suppliers?: number
  entry?: 'task' | 'work'
  /** Changes the fixture before the page loads. */
  prepare?: (f: any) => void
}
async function setup(
  page: Page,
  { suppliers: supplierCount, entry = 'task', prepare }: Options = {},
) {
  const f = JSON.parse(
    readFileSync(new URL('./fixtures/overview-pending.json', import.meta.url), 'utf8'),
  )
  const mission = f.missions.items[0]
  // The work item that carries this mission on the work page.
  const work = {
    id: 'work-one',
    store_id: mission.store_id,
    principal_id: 'test-owner',
    title: mission.objective,
    status: 'RESULT_READY',
    version: 1,
    summary: '',
    next_step: '',
    question: null,
    result: null,
    mission_id: mission.id,
    mission_request: null,
    demonstration: false,
    processor_available: false,
    processing_expires_at: null,
    created_at: '2026-10-02T00:00:00Z',
    updated_at: '2026-10-02T00:00:00Z',
    mission,
    business: null,
  }
  if (supplierCount)
    f.catalog.offers = Array.from({ length: supplierCount }, (_, i) => ({
      ...f.catalog.offers[0],
      supplier_id: 'supplier-' + (i + 1),
      sku_id: mission.sku_id,
    }))
  f.plan.expires_at = '2099-01-01T00:00:00Z'
  const candidate = (id: string, quantity: number, spend: number, lost: number) => ({
    id,
    supplier_id: quantity ? 'supplier-b' : null,
    quantity,
    spend_minor: spend,
    cash_after_minor: 80000 - spend,
    lost_qty: lost,
    end_stock: 20,
    feasible: true,
    executable: quantity > 0,
    rejection_reasons: [],
    daily: [],
  })
  const c = {
    item: null as any,
    loseMaterialize: false,
    writes: [] as { path: string; key: string | undefined; body: any }[],
  }
  const analyze = () => {
    c.item.status = 'OPTIONS_READY'
    c.item.proposal = {
      id: 'proposal-' + c.item.current_revision,
      case_id: c.item.id,
      revision: c.item.current_revision,
      snapshot_hash: 'snapshot',
      candidate_set_hash: 'candidates',
      proposal_hash: 'proposal-hash',
      recommended_candidate_id: c.item.budget_minor >= 24000 ? 'b20' : 'wait',
      candidates: [
        candidate('wait', 0, 0, 20),
        {
          ...candidate('b20', 20, 24000, 0),
          feasible: c.item.budget_minor >= 24000,
          executable: c.item.budget_minor >= 24000,
          rejection_reasons: c.item.budget_minor >= 24000 ? [] : ['BUDGET_EXCEEDED'],
        },
      ],
      expires_at: '2099-01-01T00:00:00Z',
    }
  }
  await page.route('**/api/**', async (route) => {
    const r = route.request(),
      u = new URL(r.url()),
      path = u.pathname.replace('/api/backend/api/v1/', '')
    if (u.pathname === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: 'test-owner',
          roles: ['admin'],
          agentEnabled: false,
          devTools: false,
          workIntake: entry === 'work',
          planRevision: true,
          recoveryCases: true,
        },
      })
    if (r.method() !== 'GET') {
      const body = r.postDataJSON()
      c.writes.push({ path, key: r.headers()['idempotency-key'], body })
      if (path === 'operations-cases') {
        c.item = {
          ...body,
          id: 'case-one',
          store_id: mission.store_id,
          sku_id: mission.sku_id,
          status: 'OPEN',
          current_revision: 1,
          current_mission_version: mission.mission_version,
          current_state_version: f.dashboard.state.state_version,
          current_plan_id: mission.current_plan_id,
          proposal: null,
          plan_id: null,
          plan_status: null,
          plan_revision: null,
          action_id: null,
          execution_status: null,
          missing_inputs: [],
          evidence: [],
          created_at: '2026-10-02T00:00:00Z',
          updated_at: '2026-10-02T00:00:00Z',
        }
      } else if (path.endsWith('/analyze')) analyze()
      else if (path.endsWith('/revise')) {
        c.item = {
          ...c.item,
          ...body,
          current_revision: c.item.current_revision + 1,
          status: 'OPEN',
          proposal: null,
          plan_status: c.item.plan_id ? 'SUPERSEDED' : null,
        }
      } else if (path.endsWith('/materialize')) {
        if (c.loseMaterialize) {
          c.loseMaterialize = false
          return route.abort('connectionreset')
        }
        c.item.plan_id = 'recovery-plan'
        c.item.status = 'MONITORING'
        c.item.plan_status = 'PENDING_APPROVAL'
        c.item.plan_revision = c.item.current_revision
        // The adopted quote becomes the mission's plan awaiting confirmation. Another
        // supplier quoted the same quantity, so only the adopted id tells them apart.
        f.plan = {
          ...f.plan,
          id: 'recovery-plan',
          plan_kind: 'recovery_v1',
          selected_candidate_id: 'b20',
          proposed_purchase: {
            ...f.plan.proposed_purchase,
            supplier_id: 'supplier-b',
            quantity: 20,
            unit_price_minor: 1200,
            total_minor: 24000,
          },
          input_snapshot: {
            ...f.plan.input_snapshot,
            offer: {
              ...f.plan.input_snapshot.offer,
              supplier_id: 'supplier-b',
              unit_price_minor: 1200,
            },
          },
          candidates: [
            { ...candidate('a20', 20, 18000, 9), supplier_id: 'supplier-a', shortage_qty: 9 },
            { ...candidate('b20', 20, 24000, 0), shortage_qty: 0 },
            { ...candidate('wait', 0, 0, 20), shortage_qty: 20 },
          ],
        }
        mission.current_plan_id = 'recovery-plan'
      } else if (path.endsWith('/control')) {
        if (body.operation === 'cancel') c.item.status = 'CANCELLED'
        if (body.operation === 'refresh') {
          c.item.current_revision++
          c.item.status = 'OPEN'
          c.item.proposal = null
          c.item.stale = false
        }
        if (body.operation === 'enable_followup') c.item.followup_enabled = true
        if (body.operation === 'disable_followup') c.item.followup_enabled = false
      } else if (path.endsWith('/partial-acceptance')) {
        const action = f.actions.items.find(
          (a: any) => path === `actions/${a.id}/partial-acceptance`,
        )
        action.status = 'SUCCEEDED'
        return route.fulfill({ json: action })
      } else
        return route.fulfill({
          status: 409,
          json: { error: { code: 'BLOCKED_TEST_WRITE', message: path } },
        })
      return route.fulfill({ status: path === 'operations-cases' ? 201 : 200, json: c.item })
    }
    if (path === 'operations-cases')
      return route.fulfill({ json: { items: c.item ? [c.item] : [], next_cursor: null } })
    if (path === 'operations-cases/case-one') return route.fulfill({ json: c.item })
    if (path === 'work-items')
      return route.fulfill({
        json: { items: [work], next_cursor: null, processor_available: false },
      })
    if (path === 'work-items/work-one') return route.fulfill({ json: { item: work, messages: [] } })
    if (path === 'stores')
      return route.fulfill({
        json: {
          items: [{ store_id: mission.store_id, currency: 'CNY', source_type: 'simulation' }],
          active_store: { store_id: mission.store_id },
          next_cursor: null,
        },
      })
    if (path === `missions/${mission.id}`) return route.fulfill({ json: mission })
    if (path.endsWith('/timeline')) return route.fulfill({ json: f.timeline })
    if (path.endsWith('/plans'))
      return route.fulfill({ json: { items: [f.plan], next_cursor: null } })
    if (path.startsWith('plans/')) return route.fulfill({ json: f.plan })
    if (f[path]) return route.fulfill({ json: f[path] })
    return route.fulfill({
      status: 404,
      json: { error: { code: 'MISSING_TEST_READ', message: path } },
    })
  })
  prepare?.(f)
  if (entry === 'work') {
    await page.goto('/?view=work&item=' + work.id + '&store=' + mission.store_id)
    await expect(page.locator('.space-workspace.task-workspace')).toBeVisible()
  } else {
    await page.goto('/?view=task&mission=' + mission.id + '&store=' + mission.store_id)
    await expect(page.locator('.task-workspace')).toBeVisible()
  }
  await page.getByRole('button', { name: '供应异常应对', exact: true }).click({ timeout: 5000 })
  return c
}

test('分析只产生候选，选择后生成待确认计划，不批准采购', async ({ page }) => {
  const c = await setup(page)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  const row = page.locator('[data-recovery-candidate="b20"]')
  await expect(row).toContainText('240')
  await expect(row).toContainText('推荐')
  expect(c.writes.map((r) => r.path)).toEqual([
    'operations-cases',
    'operations-cases/case-one/analyze',
  ])
  await row.getByRole('button', { name: '生成待确认方案' }).click()
  await expect(
    page.getByText('恢复方案已生成，采购仍需在原方案卡中确认。', { exact: true }),
  ).toBeVisible()
  const write = c.writes.at(-1)!
  expect(write.path).toBe('operations-cases/case-one/materialize')
  expect(write.body).toMatchObject({
    candidate_id: 'b20',
    expected_revision: 1,
    proposal_hash: 'proposal-hash',
  })
  expect(c.writes.some((r) => r.path.endsWith('/decision'))).toBe(false)
})

test('预算改口使旧候选失效，重新分析后不能采用超预算方案', async ({ page }) => {
  await setup(page)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await expect(page.locator('[data-recovery-candidate="b20"]')).toBeVisible()
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('200')
  await page.getByRole('button', { name: '按新要求重新分析', exact: true }).click()
  await expect(page.locator('[data-recovery-candidate="wait"]')).toContainText('推荐')
  await expect(
    page.locator('[data-recovery-candidate="b20"]').getByRole('button', { name: '生成待确认方案' }),
  ).toBeDisabled()
})

test('采用请求丢响应后重试同一请求和幂等键', async ({ page }) => {
  const c = await setup(page)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  c.loseMaterialize = true
  await page
    .locator('[data-recovery-candidate="b20"]')
    .getByRole('button', { name: '生成待确认方案' })
    .click()
  await expect(page.getByRole('button', { name: '核实并重试原提交' })).toBeVisible()
  await page.getByRole('button', { name: '核实并重试原提交' }).click()
  await expect(
    page.getByText('恢复方案已生成，采购仍需在原方案卡中确认。', { exact: true }),
  ).toBeVisible()
  const writes = c.writes.filter((r) => r.path.endsWith('/materialize'))
  expect(writes).toHaveLength(2)
  expect(writes[0].key).toBe(writes[1].key)
  expect(writes[0].body).toEqual(writes[1].body)
})

test('非法金额与不完整七日需求不发送请求', async ({ page }) => {
  const c = await setup(page)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('20.001')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await expect(page.locator('.recovery-workspace [role="alert"]')).toContainText('最多两位小数')
  expect(c.writes).toHaveLength(0)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByText('补充七日需求情景（没有可用日预测时填写）', { exact: true }).click()
  await page.getByLabel('七日需求（件，逗号分隔）').fill('10,20')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await expect(page.locator('.recovery-workspace [role="alert"]')).toContainText('七个非负整数')
  expect(c.writes).toHaveLength(0)
})

test('依据已过期时禁用采用，后台刷新保留正在编辑的预算', async ({ page }) => {
  const c = await setup(page)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  const adopt = page
    .locator('[data-recovery-candidate="b20"]')
    .getByRole('button', { name: '生成待确认方案' })
  await expect(adopt).toBeEnabled()
  c.item.stale = true
  await page.getByRole('button', { name: '刷新处理状态', exact: true }).click()
  await expect(adopt).toBeDisabled({ timeout: 3000 })
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('150')
  await page.getByRole('button', { name: '刷新处理状态', exact: true }).click()
  await expect(page.getByLabel('本次应急预算（元）', { exact: true })).toHaveValue('150')
})

test('旧计划被修订后仍可采用新候选；核对最新依据创建新版本', async ({ page }) => {
  const c = await setup(page)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  const adopt = page
    .locator('[data-recovery-candidate="b20"]')
    .getByRole('button', { name: '生成待确认方案' })
  await adopt.click()
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('250')
  await page.getByRole('button', { name: '按新要求重新分析', exact: true }).click()
  await expect(adopt).toBeEnabled({ timeout: 3000 })
  c.item.stale = true
  await page.getByRole('button', { name: '刷新处理状态', exact: true }).click()
  await page.getByRole('button', { name: '重新核对最新依据', exact: true }).click()
  await expect(adopt).toBeEnabled({ timeout: 3000 })
  expect(c.writes.slice(-2).map((r) => r.path.split('/').at(-1))).toEqual(['control', 'analyze'])
})

test('结束事项后可新建独立事项，自动跟进由用户开启关闭', async ({ page }) => {
  const c = await setup(page)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await page.getByRole('button', { name: '开启自动跟进', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止自动跟进', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '停止自动跟进', exact: true }).click()
  await page.getByRole('button', { name: '结束这项恢复事项', exact: true }).click()
  await page.getByRole('button', { name: '新建恢复事项', exact: true }).click({ timeout: 3000 })
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('200')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  expect(c.writes.filter((r) => r.path === 'operations-cases')).toHaveLength(2)
})

test('超过三家报价时要求选择范围并传递供应商名单', async ({ page }) => {
  const c = await setup(page, { suppliers: 4 })
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await expect(page.locator('.recovery-workspace [role="alert"]')).toContainText('一至三家供应商')
  expect(c.writes).toHaveLength(0)
  await page.getByRole('checkbox', { name: 'supplier-1', exact: true }).check()
  await page.getByRole('checkbox', { name: 'supplier-3', exact: true }).check()
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await expect(page.locator('[data-recovery-candidate="b20"]')).toBeVisible()
  expect(c.writes[0].body.supplier_ids).toEqual(['supplier-1', 'supplier-3'])
})

test('从事项页进入：采用报价后方案卡只给已采纳的报价或本轮不补', async ({ page }) => {
  const c = await setup(page, { entry: 'work' })
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await page
    .locator('[data-recovery-candidate="b20"]')
    .getByRole('button', { name: '生成待确认方案' })
    .click()
  const card = page.locator('#space-plan .space-plan-card')
  await expect(card).toContainText('这份待确认方案对应已采纳的报价', { timeout: 5000 })
  // Two quotes share the quantity; the amounts are the adopted supplier's.
  await expect(card.locator('.impact-value').nth(1)).toHaveText('¥240')
  const options = card.getByRole('group', { name: '采购选项' }).getByRole('button')
  await expect(options).toHaveCount(2)
  await expect(options.nth(1)).toContainText('本轮暂不补货')
  expect(c.writes.some((r) => r.path.endsWith('/decision'))).toBe(false)
})

test('从事项页进入：店主自己发出的订单在方案位置等待回复，状态写待供应商确认', async ({ page }) => {
  const c = await setup(page, {
    entry: 'work',
    prepare: (f) => {
      const mission = f.missions.items[0]
      const order = {
        reference: 'PO-1A2B3C4D',
        supplier_id: 'supplier-b',
        sku_id: mission.sku_id,
        product_name: f.catalog.products[0].name,
        quantity: 20,
        unit_price_minor: 1200,
        total_minor: 24000,
        currency: 'CNY',
        requested_delivery_date: '2026-10-05',
        text: {
          zh: '你好，订购 20 件，单价 12.00 元。订单编号 PO-1A2B3C4D',
          en: 'Order 20 units.',
        },
        generated_at: '2026-10-02T00:00:00Z',
      }
      f.actions.items = [
        {
          id: 'action-by-hand',
          mission_id: mission.id,
          plan_id: f.plan.id,
          approval_id: 'approval-one',
          status: 'EXECUTING',
          channel: 'assisted',
          quantity: 20,
          amount_minor: 24000,
          currency: 'CNY',
          external_order_id: null,
          receipt: null,
          last_error: null,
          order_message: order,
          supplier_reply: null,
          created_at: '2026-10-02T00:00:00Z',
          updated_at: '2026-10-02T00:00:00Z',
          purchase_snapshot: {
            ...f.plan.proposed_purchase,
            quantity: 20,
            total_minor: 24000,
            expected_arrival_at: '2026-10-05T00:00:00Z',
          },
        },
      ]
      mission.current_action_id = 'action-by-hand'
      f.plan.status = 'APPROVED'
    },
  })
  const order = page.locator('#space-plan [data-assisted-order]')
  await expect(order).toBeVisible({ timeout: 5000 })
  await expect(order.locator('[data-order-message]')).toContainText('PO-1A2B3C4D')
  await expect(page.locator('.space-workspace .tag.amber[role="status"]').first()).toHaveText(
    '待供应商确认',
  )
  await expect(page.locator('.space-orders')).toContainText('待供应商确认')
  await expect(page.locator('.space-orders')).not.toContainText('正在核实采购')
  expect(c.writes).toHaveLength(0)
})

test('事项结束时写明补了多少、花了多少、缺货降了多少；需要重新分析时写明原因', async ({ page }) => {
  const c = await setup(page)
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await expect(page.locator('[data-recovery-candidate="b20"]')).toBeVisible()
  c.item.status = 'RECHECK_REQUIRED'
  c.item.recheck_reason = 'BUSINESS_STATE_CHANGED'
  await page.getByRole('button', { name: '刷新处理状态', exact: true }).click()
  await expect(page.locator('[data-recheck-reason]')).toContainText('库存、现金或营业时间已变化')
  c.item.status = 'RESOLVED'
  c.item.recheck_reason = null
  c.item.outcome = {
    path: 'purchase',
    planned_qty: 20,
    purchased_qty: 20,
    received_qty: 20,
    spend_minor: 24000,
    lost_qty_before: 20,
    lost_qty_after: 0,
    action_ids: ['action-one'],
  }
  await page.getByRole('button', { name: '刷新处理状态', exact: true }).click()
  const outcome = page.locator('[data-recovery-outcome]')
  await expect(outcome).toContainText('20 件 → 0 件', { timeout: 3000 })
  await expect(outcome).toContainText('¥240')
  await expect(page.locator('.recovery-heading h3')).toHaveText('已解决')
  await expect(page.getByRole('button', { name: '结束这项恢复事项' })).toHaveCount(0)
})

test('供应商只确认一部分：事项里缺的部分向其他供应商重新比较', async ({ page }) => {
  const c = await setup(page, { suppliers: 3 })
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  await expect(page.locator('[data-recovery-candidate="b20"]')).toBeVisible()
  c.item.status = 'MONITORING'
  c.item.purchases = [
    {
      action_id: 'action-one',
      supplier_id: 'supplier-2',
      status: 'SUCCEEDED',
      planned_qty: 20,
      accepted_qty: 10,
      received_qty: 0,
    },
  ]
  await page.getByRole('button', { name: '刷新处理状态', exact: true }).click()
  const shortfall = page.locator('[data-recovery-shortfall]')
  await expect(shortfall).toContainText('还缺 10 件', { timeout: 3000 })
  await shortfall.getByRole('button', { name: '缺的找别家补上' }).click()
  await expect
    .poll(() => c.writes.slice(-2).map((r) => r.path.split('/').at(-1)))
    .toEqual(['revise', 'analyze'])
  const revise = c.writes.at(-2)
  expect(revise!.body.supplier_ids).toEqual(['supplier-1', 'supplier-3'])
})

test('从事项页进入：供应商只确认一部分时可按对方数量成交', async ({ page }) => {
  const c = await setup(page, {
    entry: 'work',
    prepare: (f) => {
      const mission = f.missions.items[0]
      f.actions.items = [
        {
          id: 'action-by-hand',
          mission_id: mission.id,
          plan_id: f.plan.id,
          approval_id: 'approval-one',
          status: 'EXECUTING',
          channel: 'assisted',
          quantity: 20,
          amount_minor: 24000,
          currency: 'CNY',
          external_order_id: null,
          receipt: null,
          last_error: null,
          order_message: {
            reference: 'PO-1A2B3C4D',
            supplier_id: 'supplier-b',
            sku_id: mission.sku_id,
            product_name: f.catalog.products[0].name,
            quantity: 20,
            unit_price_minor: 1200,
            total_minor: 24000,
            currency: 'CNY',
            requested_delivery_date: '2026-10-05',
            text: { zh: '你好，订购 20 件。订单编号 PO-1A2B3C4D', en: 'Order 20 units.' },
            generated_at: '2026-10-02T00:00:00Z',
          },
          supplier_reply: {
            text: '可以，但只有10件',
            read_by: 'rules',
            outcome: 'partial',
            decision: 'accepted',
            quantity: 10,
            unit_price_minor: null,
            total_minor: null,
            delivery_date: null,
            supplier_order_ref: null,
            quotes: { decision: '可以', quantity: '10件' },
            differences: [{ field: 'quantity', ordered: 20, replied: 10 }],
            recorded_at: '2026-10-02T01:00:00Z',
            recorded_by: 'test-owner',
          },
          created_at: '2026-10-02T00:00:00Z',
          updated_at: '2026-10-02T01:00:00Z',
          purchase_snapshot: {
            ...f.plan.proposed_purchase,
            quantity: 20,
            total_minor: 24000,
            expected_arrival_at: '2026-10-05T00:00:00Z',
          },
        },
      ]
      mission.current_action_id = 'action-by-hand'
      f.plan.status = 'APPROVED'
    },
  })
  const order = page.locator('#space-plan [data-assisted-order]')
  await expect(order.locator('.supplier-receipt')).toContainText('只确认了一部分', {
    timeout: 5000,
  })
  const accept = order.locator('[data-accept-partial]')
  await expect(accept).toHaveText('按对方数量成交（10 件）')
  await accept.click()
  await expect
    .poll(() => c.writes.map((r) => r.path))
    .toContain('actions/action-by-hand/partial-acceptance')
})
