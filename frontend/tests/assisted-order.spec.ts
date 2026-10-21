import { test, expect, type Page } from '@playwright/test'
import { setupRecovery, type Mock } from './support/recovery-mock'

// A regular order the owner sends by hand (assisted channel), on the work page, against the
// stateful mock. The backend's background behaviour is added here: an owner write moves the state
// version at once, and the new plan follows a few seconds later. No purchase reaches a supplier.

/** The business line the work item carries, as work_items/business.py writes it. */
const business = (m: Mock, code: string, detail: string, priority: number, extra = {}) => ({
  code,
  label: code,
  detail,
  tone: priority < 40 ? 'amber' : 'blue',
  priority,
  action_label: '查看备货',
  needs_attention: priority < 40,
  can_confirm: false,
  state_version: m.f.dashboard.state.state_version,
  mission_version: m.mission.mission_version,
  plan_id: m.f.plan.id,
  observed_at: new Date().toISOString(),
  ...extra,
})

/** The plan the backend works out after the facts moved: `quantity` to buy, `gap` with none. */
function nextPlan(m: Mock, quantity: number | null, gap: number) {
  const previous = structuredClone(m.f.plan)
  const plan = structuredClone(m.f.plan)
  plan.id = `plan-v${previous.plan_version + 1}`
  plan.plan_version = previous.plan_version + 1
  plan.status = 'PENDING_APPROVAL'
  plan.state_version = m.f.dashboard.state.state_version
  plan.expires_at = '2099-01-01T00:00:00Z'
  plan.proposed_purchase = quantity
    ? { ...m.f.plan.proposed_purchase, quantity, total_minor: quantity * 1000 }
    : null
  plan.candidates = plan.candidates.map((c: any) => ({
    ...c,
    shortage_qty: Math.max(0, gap - c.quantity),
  }))
  m.plans[previous.id] = previous
  m.plans[plan.id] = plan
  m.f.plan = plan
  m.mission.current_plan_id = plan.id
  ;(m as any).previous = previous
}

/** The regular plan approved for `quantity` units; its order waits for the supplier's reply. */
async function start(page: Page, quantity: number, devTools = false) {
  if (devTools)
    await page.addInitScript(() =>
      localStorage.setItem('ss.scenarios', JSON.stringify({ 'overview-fixture-a': 'run-one' })),
    )
  const m = await setupRecovery(page, {
    prepare: (f, mock) => {
      mock.session.devTools = devTools
      const mission = f.missions.items[0]
      const purchase = { ...f.plan.proposed_purchase, quantity, total_minor: quantity * 1000 }
      f.plan.proposed_purchase = purchase
      f.plan.status = 'APPROVED'
      f.actions.items = [
        {
          id: 'action-regular',
          mission_id: mission.id,
          plan_id: f.plan.id,
          approval_id: 'approval-one',
          status: 'EXECUTING',
          channel: 'assisted',
          quantity,
          amount_minor: quantity * 1000,
          currency: 'CNY',
          external_order_id: null,
          receipt: null,
          last_error: null,
          order_message: {
            reference: 'PO-1A2B3C4D',
            supplier_id: purchase.supplier_id,
            sku_id: mission.sku_id,
            product_name: f.catalog.products[0].name,
            quantity,
            unit_price_minor: 1000,
            total_minor: quantity * 1000,
            currency: 'CNY',
            requested_delivery_date: purchase.expected_arrival_at.slice(0, 10),
            text: { zh: `订购 ${quantity} 件。订单编号 PO-1A2B3C4D`, en: 'Order.' },
            generated_at: '2026-10-02T00:00:00Z',
          },
          supplier_reply: null,
          created_at: '2026-10-02T00:00:00Z',
          updated_at: '2026-10-02T00:00:00Z',
          purchase_snapshot: { ...purchase },
        },
      ]
      mission.current_action_id = 'action-regular'
      mock.work.business = business(
        mock,
        'AWAITING_SUPPLIER',
        '订单信息已生成，请用你自己的渠道发给供应商，收到回复后贴回这件事里。',
        30,
      )
    },
  })
  await page.route('**/api/backend/api/v1/missions/*/plans*', (route) =>
    route.fulfill({
      json: { items: [m.f.plan, (m as any).previous].filter(Boolean), next_cursor: null },
    }),
  )
  await page.route('**/api/backend/dev/v1/scenarios/*/advance', (route) => {
    m.f.dashboard.state.state_version++
    return route.fulfill({ status: 202, json: { job_run_id: 'advance-job' } })
  })
  await page.route('**/api/backend/api/v1/job-runs/advance-job', (route) =>
    route.fulfill({ json: { id: 'advance-job', status: 'SUCCEEDED' } }),
  )
  return m
}

/** The reply is read in a moment; the state moves as the backend records it. */
async function readReplySlowly(page: Page, m: Mock) {
  await page.route('**/actions/action-regular/supplier-reply', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800))
    m.f.dashboard.state.state_version++
    await route.fallback()
  })
}

test('确认回复：读取时只在卡片里说进度；回执留在原位成为到货卡，不闪发单前的文案', async ({
  page,
}) => {
  const m = await start(page, 40)
  await readReplySlowly(page, m)
  const order = page.locator('#space-plan [data-assisted-order]')
  await order.locator('[data-supplier-reply]').fill('好的，40 件没问题，明天到。')
  await order.getByRole('button', { name: '登记回复', exact: true }).click()
  await expect(order.getByRole('status')).toHaveText('正在读取回复…')
  await expect(page.locator('.toast')).toHaveCount(0)
  // The order's next step takes its place, headed by what was read from the reply.
  const arrival = page.locator('#space-plan [data-arrival-card]')
  await expect(arrival.locator('.supplier-receipt')).toContainText('回执 · 供应商已确认')
  await expect(page.locator('[data-arrival-card]')).toHaveCount(1)
  await expect(page.locator('.task-result-column')).not.toContainText('收到回复后贴回')
  await expect(page.locator('.task-heading-actions > .tag')).toHaveText('货到后请登记')
  // The new plan proposes nothing more: the arrival card keeps the slot.
  nextPlan(m, null, 0)
  await expect(page.locator('.plan-change-receipt')).toBeVisible({ timeout: 10000 })
  await expect(arrival).toBeVisible()
  await expect(page.locator('.space-plan-card')).toHaveCount(0)
})

test('拒单：回执留到店主下一步，后台刷新不替换；常规方案收成一行，今日页只有一个拍板', async ({
  page,
}) => {
  const m = await start(page, 20)
  await readReplySlowly(page, m)
  const order = page.locator('#space-plan [data-assisted-order]')
  await order.locator('[data-supplier-reply]').fill('抱歉，这批没货了。')
  await order.getByRole('button', { name: '登记回复', exact: true }).click()
  const declined = page.locator('#space-plan [data-declined-order]')
  await expect(declined.locator('.supplier-receipt')).toContainText('回执 · 供应商未接单')
  await expect(declined.locator('[data-declined-restock]')).toHaveText('找别家补')
  // The backend's next plan (same supplier) arrives with a background refresh.
  nextPlan(m, 20, 40)
  m.work.business = business(m, 'PENDING_APPROVAL', '先核对数量。', 10, { can_confirm: true })
  const line = page.locator('#space-plan [data-regular-plan-line]')
  await expect(line).toContainText('常规方案：建议补 20 件', { timeout: 10000 })
  await expect(declined).toBeVisible()
  await expect(page.locator('.space-plan-card')).toHaveCount(0)
  await expect(page.locator('.task-result-column .primary:visible')).toHaveCount(1)
  // The owner's next step lets the receipt go: reviewing the regular plan opens it in full.
  await line.getByRole('button').click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('核对这笔采购')
  await dialog.getByRole('button', { name: '返回修改', exact: true }).click()
  await expect(page.locator('.space-plan-card')).toBeVisible()
  await expect(page.locator('[data-declined-order]')).toHaveCount(0)
  // Today: the decline leads; the regular plan of the same mission is one line under it.
  await page.getByRole('button', { name: '返回今日', exact: true }).click()
  const zone = page.locator('#decision-zone')
  await expect(zone.locator('[data-recovery-prompt]')).toBeVisible()
  await expect(zone.locator('[data-regular-plan-line]')).toContainText('核对 20 件采购')
  await expect(zone.locator('.work-card')).toHaveCount(0)
  await expect(zone.locator('.primary:visible')).toHaveCount(1)
  await expect(zone.locator('.section-label .small-count').first()).toHaveText('1')
  // The line does what the work page's same line does: the review opens, over the item.
  await zone.locator('[data-regular-plan-line]').getByRole('button').click()
  await expect(page.getByRole('dialog')).toContainText('核对这笔采购')
  await expect(page.locator('.space-workspace.task-workspace')).toBeVisible()
})

test('登记到货后的重算窗口：保留方案卡并暂停，不出“需要处理”卡，新方案到了再恢复', async ({
  page,
}) => {
  const m = await start(page, 40)
  const order = page.locator('#space-plan [data-assisted-order]')
  await order.locator('[data-supplier-reply]').fill('好的，40 件没问题，明天到。')
  await order.getByRole('button', { name: '登记回复', exact: true }).click()
  await expect(page.locator('[data-arrival-card]')).toBeVisible()
  m.f.dashboard.state.state_version++
  nextPlan(m, 20, 40)
  const review = page.getByRole('button', { name: '核对 20 件采购', exact: true })
  await expect(review).toBeEnabled({ timeout: 10000 })
  await page.route('**/actions/action-regular/arrival', async (route) => {
    m.f.dashboard.state.state_version++
    await route.fallback()
  })
  await page.locator('[data-record-arrival]').click()
  await expect(page.getByRole('status').filter({ hasText: '正在重新核对方案…' })).toBeVisible()
  await expect(review).toBeDisabled()
  await expect(page.locator('.space-issue')).toHaveCount(0)
  await expect(page.locator('.task-heading-actions > .tag')).not.toHaveText('需要处理')
  nextPlan(m, null, 0)
  await expect(page.getByText('正在重新核对方案…', { exact: true })).toHaveCount(0, {
    timeout: 10000,
  })
  await expect(page.locator('.space-issue')).toHaveCount(0)
  await expect(page.locator('.space-outcome')).toBeVisible()
})

test('登记到货、没有方案可拍板时的重算窗口：状态卡自己说正在核对，不沿用“旧方案不能确认”', async ({
  page,
}) => {
  const m = await start(page, 40)
  const order = page.locator('#space-plan [data-assisted-order]')
  await order.locator('[data-supplier-reply]').fill('好的，40 件没问题，明天到。')
  await order.getByRole('button', { name: '登记回复', exact: true }).click()
  await expect(page.locator('#space-plan [data-arrival-card]')).toBeVisible()
  // The plan after the reply buys nothing more: the arrival keeps the slot.
  m.f.dashboard.state.state_version++
  nextPlan(m, null, 0)
  await expect(page.locator('.plan-change-receipt')).toBeVisible({ timeout: 10000 })
  // As the backend: recording moves the facts, and until the new plan arrives the item's plan is
  // "to be updated" (work_items/business.py PLAN_STALE).
  await page.route('**/actions/action-regular/arrival', async (route) => {
    m.f.dashboard.state.state_version++
    m.work.business = business(
      m,
      'PLAN_STALE',
      '经营数据、条件或有效期已变化，旧方案不能确认。',
      15,
    )
    await route.fallback()
  })
  await page.locator('[data-record-arrival]').click()
  const outcome = page.locator('#space-plan .space-outcome')
  await expect(outcome.getByRole('status')).toHaveText('正在重新核对方案…')
  await expect(page.locator('#space-plan').getByText('正在重新核对方案…')).toHaveCount(1)
  await expect(outcome).not.toContainText('旧方案不能确认')
  await expect(page.locator('.space-issue')).toHaveCount(0)
  // The new plan lands while the item's line still calls the old one "to be updated": the card
  // keeps the re-check line instead of that sentence until the line catches up.
  const height = await outcome.evaluate((el) => el.getBoundingClientRect().height)
  nextPlan(m, null, 0)
  await page.waitForResponse((r) => r.url().endsWith('/plans/' + m.f.plan.id))
  await page.waitForTimeout(300)
  await expect(outcome.getByRole('status')).toHaveText('正在重新核对方案…')
  await expect(outcome).not.toContainText('旧方案不能确认')
  // Then the card's own line takes the place of the re-check line: the card keeps its size.
  m.work.business = business(m, 'FOLLOWING', '等待下一次业务检查；有新的可行方案时再请你确认。', 70)
  await expect(outcome).toContainText('等待下一次业务检查', { timeout: 10000 })
  await expect(outcome.getByRole('status')).toHaveCount(0)
  expect(await outcome.evaluate((el) => el.getBoundingClientRect().height)).toBe(height)
})

test('推进经营事件：当前方案不补货时保留原来的状态卡，不出现“建议补货 0 件”', async ({ page }) => {
  const m = await start(page, 40, true)
  const order = page.locator('#space-plan [data-assisted-order]')
  await order.locator('[data-supplier-reply]').fill('好的，40 件没问题，明天到。')
  await order.getByRole('button', { name: '登记回复', exact: true }).click()
  m.f.dashboard.state.state_version++
  nextPlan(m, null, 0)
  await expect(page.locator('.plan-change-receipt')).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: '联调控制 · 合成数据', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: '推进下一个经营事件' }).click()
  await expect(page.getByRole('status').filter({ hasText: '正在重新核对方案…' })).toBeVisible()
  await expect(page.locator('#space-plan [data-arrival-card]')).toBeVisible()
  await expect(page.locator('.space-plan-card')).toHaveCount(0)
  await expect(page.locator('.space-issue')).toHaveCount(0)
  nextPlan(m, 20, 40)
  await expect(page.getByRole('button', { name: '核对 20 件采购', exact: true })).toBeEnabled({
    timeout: 10000,
  })
  await expect(page.getByText('正在重新核对方案…', { exact: true })).toHaveCount(0)
  await expect(page.locator('.plan-change-receipt')).toContainText('20/40 件')
})

/** "Next day" from the developer controls (the presenter bar does the same in demo mode). */
async function advance(page: Page) {
  await page.getByRole('button', { name: '联调控制 · 合成数据', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: '推进下一个经营事件' }).click()
}

/** Where an element sits on the page, whatever the scroll. */
const pageTop = (locator: ReturnType<Page['locator']>) =>
  locator.evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY))

test('有在途货时推进：方案卡保留并暂停，到货卡仍是次要的，不展开回执、不把方案槽往下推', async ({
  page,
}) => {
  const m = await start(page, 40, true)
  const order = page.locator('#space-plan [data-assisted-order]')
  await order.locator('[data-supplier-reply]').fill('好的，40 件没问题，明天到。')
  await order.getByRole('button', { name: '登记回复', exact: true }).click()
  const arrival = page.locator('[data-arrival-card]')
  await expect(arrival).toBeVisible()
  m.f.dashboard.state.state_version++
  nextPlan(m, 20, 40)
  const review = page.getByRole('button', { name: '核对 20 件采购', exact: true })
  await expect(review).toBeEnabled({ timeout: 10000 })
  // A plan to decide holds the one primary action; the goods on the way wait above it, compact.
  await expect(arrival.locator('.supplier-receipt')).toHaveCount(0)
  await expect(arrival.locator('.primary')).toHaveCount(0)
  const slot = page.locator('#space-plan')
  const before = await pageTop(slot)
  await advance(page)
  await expect(page.getByRole('status').filter({ hasText: '正在重新核对方案…' })).toBeVisible()
  await expect(review).toBeDisabled()
  await expect(arrival.locator('.supplier-receipt')).toHaveCount(0)
  await expect(arrival.locator('.primary')).toHaveCount(0)
  expect(await pageTop(slot)).toBe(before)
  nextPlan(m, 20, 40)
  await expect(review).toBeEnabled({ timeout: 10000 })
  await expect(arrival.locator('.primary')).toHaveCount(0)
})

test('登记到货后的重算窗口过了，新方案仍没到：问题卡照常出现，不掩盖真实故障', async ({ page }) => {
  await page.clock.install()
  const m = await start(page, 40)
  const order = page.locator('#space-plan [data-assisted-order]')
  await order.locator('[data-supplier-reply]').fill('好的，40 件没问题，明天到。')
  await order.getByRole('button', { name: '登记回复', exact: true }).click()
  await expect(page.locator('[data-arrival-card]')).toBeVisible()
  m.f.dashboard.state.state_version++
  nextPlan(m, 20, 40)
  const review = page.getByRole('button', { name: '核对 20 件采购', exact: true })
  await expect(review).toBeEnabled({ timeout: 10000 })
  await page.route('**/actions/action-regular/arrival', async (route) => {
    m.f.dashboard.state.state_version++
    await route.fallback()
  })
  await page.locator('[data-record-arrival]').click()
  await expect(page.getByRole('status').filter({ hasText: '正在重新核对方案…' })).toBeVisible()
  await expect(page.locator('.space-issue')).toHaveCount(0)
  // No new plan within the owner's write window (30 s): the problem is said again.
  await page.clock.fastForward(31_000)
  await expect(page.locator('.space-issue')).toBeVisible({ timeout: 10000 })
  await expect(page.getByText('正在重新核对方案…', { exact: true })).toHaveCount(0)
  await expect(page.locator('.task-heading-actions > .tag')).toHaveText('需要处理')
})

test('今日页推进：重算窗口内不出“需要处理”，事项卡原样保留并说正在核对；窗口过了问题照常出现', async ({
  page,
}) => {
  await page.clock.install()
  await page.addInitScript(() =>
    localStorage.setItem('ss.scenarios', JSON.stringify({ 'overview-fixture-a': 'run-one' })),
  )
  const m = await setupRecovery(page, {
    entry: 'today',
    prepare: (_f, mock) => {
      mock.session.devTools = true
      mock.work.business = business(mock, 'PENDING_APPROVAL', '先核对数量。', 10, {
        can_confirm: true,
        action_label: '核对采购方案',
      })
    },
  })
  // As the backend: the facts move, and until the new plan arrives the item's plan is "to be
  // updated" (work_items/business.py PLAN_STALE).
  await page.route('**/api/backend/dev/v1/scenarios/*/advance', (route) => {
    m.f.dashboard.state.state_version++
    m.work.business = business(
      m,
      'PLAN_STALE',
      '经营数据、条件或有效期已变化，旧方案不能确认。',
      15,
      {
        action_label: '查看并重新检查',
      },
    )
    return route.fulfill({ status: 202, json: { job_run_id: 'advance-job' } })
  })
  await page.route('**/api/backend/api/v1/job-runs/advance-job', (route) =>
    route.fulfill({ json: { id: 'advance-job', status: 'SUCCEEDED' } }),
  )
  const zone = page.locator('#decision-zone')
  const card = zone.locator('.work-card[data-work-id="work-one"]')
  const count = zone.locator('.section-label .small-count').first()
  // The plan can be carried out, only it does not cover the whole gap: it leads as a full card,
  // as on the work page, and finding another supplier is the second, quieter way.
  await expect(card).toContainText('补货 20 件 · ¥200')
  await expect(zone.locator('[data-recovery-prompt] .secondary')).toHaveText('找别家补')
  await expect(zone.locator('.primary:visible')).toHaveCount(1)
  await expect(count).toHaveText('2')
  const restaled = page.waitForResponse(
    async (r) =>
      /\/work-items(\?|$)/.test(r.url()) &&
      (await r.json()).items?.[0]?.business?.code === 'PLAN_STALE',
  )
  await advance(page)
  await restaled
  await expect(card.getByRole('status')).toHaveText('正在重新核对方案…')
  await expect(card).toContainText('补货 20 件 · ¥200')
  await expect(zone.getByText('需要处理', { exact: true })).toHaveCount(0)
  await expect(zone).not.toContainText('暂时无法确认最新经营数据')
  await expect(count).toHaveText('2')
  // No new plan within the window (90 s): the item and the page say the problem again.
  await page.clock.fastForward(91_000)
  await expect(zone.locator('.attention-card').filter({ hasText: '需要处理' })).toContainText(
    '暂时无法确认最新经营数据',
    { timeout: 10000 },
  )
  await expect(card.locator('.tag')).toHaveText('需要处理')
  await expect(card.getByText('正在重新核对方案…', { exact: true })).toHaveCount(0)
})
