import { test, expect, type Page } from '@playwright/test'
import { dayLabel, setupRecovery, type Mock } from './support/recovery-mock'

// Emergency restock as one flow on the work page (workspace §18), against a stateful mock of the
// business API. No purchase reaches a supplier; every write is recorded and checked.
const DAY = 86_400_000
const flowCard = (page: Page) => page.locator('[data-recovery-flow]')
const next = (page: Page) => flowCard(page).locator('[data-recovery-next]')
const settlement = (at: number) =>
  new Date(at).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

/** From the header entry to the comparison of the sample suppliers. */
async function toComparison(page: Page) {
  await page.locator('[data-recovery-entry]').click()
  await expect(flowCard(page)).toHaveAttribute('data-stage', 'brief')
  await next(page).click()
  await expect(flowCard(page).locator('[data-recovery-option="B"]')).toBeVisible({
    timeout: 20000,
  })
}
/** Adopt the recommendation and confirm it in the page's dialog. */
async function toOrder(page: Page) {
  await toComparison(page)
  await next(page).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('核对这笔采购')
  await dialog.getByRole('button', { name: /^确认采购 \d+ 件/ }).click()
  await expect(flowCard(page)).toHaveAttribute('data-stage', 'order')
}
const writes = (m: Mock) => m.writes.map((w) => w.path)

test('入口与预填：问题、预算、需求和首日结算都已填好，演示模式自动备好资料', async ({ page }) => {
  const m = await setupRecovery(page, { demo: true })
  const entry = page.locator('[data-recovery-entry]')
  await expect(entry).toHaveText('应急补货')
  await entry.click()
  const flow = flowCard(page)
  await expect(flow).toHaveAttribute('data-stage', 'brief')
  await expect(flow.locator('.flow-step[aria-current="step"]')).toContainText('说明情况')
  await expect(flow.locator('.flow-steps .flow-actor')).toHaveText('等你')
  // The pending regular plan still leaves a gap, so the brief says so; the numbers are the
  // seven days without a purchase on the mission's assumption (60 units, 20 in stock).
  const clock = m.clock()
  await expect(flow.locator('.rf-title')).toHaveText(
    `预计缺货：不补的话 ${dayLabel(clock + 3 * DAY - 1000)} 起缺货，7 天共缺 40 件。`,
  )
  await expect(flow.locator('[data-fact="budget"] b')).toHaveText('¥700')
  await expect(flow.locator('[data-fact="budget"] small')).toHaveText('可用现金 ¥1,000 − 底线 ¥300')
  await expect(flow.locator('[data-fact="demand"] b')).toHaveText('60 件')
  const basis = flow.getByRole('group', { name: '需求按什么填' })
  await expect(basis.locator('[aria-pressed="true"]')).toHaveText('按估算')
  // The first settlement follows the business clock; it shows only when the owner edits.
  await expect(flow.locator('[data-fact="settlement"]')).toHaveCount(0)
  await flow.getByRole('button', { name: '修改' }).click()
  await expect(flow.locator('[data-fact="settlement"] b')).toHaveText(
    settlement(clock + DAY - 1000),
  )
  await flow.getByRole('button', { name: '改好了' }).click()
  await expect(flow.locator('[data-fact="documents"] b')).toHaveText('3 家')
  expect(writes(m)).toContain(`stores/${m.store}/supplier-documents/sample`)
  // Quick fill: a flat daily demand.
  await flow.getByRole('button', { name: '每天 9 件' }).click()
  await expect(flow.locator('[data-fact="demand"] b')).toHaveText('63 件')
  await expect(basis.locator('[aria-pressed="true"]')).toHaveText('每天')
  await next(page).click()
  const create = m.writes.find((w) => w.path === 'operations-cases')!
  expect(create.body).toMatchObject({ budget_minor: 70000, max_purchase_qty: null })
  expect(create.body.objective).toContain('7 天共缺 43 件')
  expect(create.body.daily_demand).toHaveLength(7)
  expect(create.body.daily_demand[0]).toEqual({
    settlement_at: new Date(clock + DAY - 1000).toISOString(),
    demand_qty: 9,
  })
  expect(create.body.daily_demand[6].settlement_at).toBe(
    new Date(clock + 7 * DAY - 1000).toISOString(),
  )
  await expect
    .poll(() => writes(m).slice(-3))
    .toEqual([
      'operations-cases',
      'operations-cases/case-one/analyze',
      'operations-cases/case-one/source',
    ])
  // Reviewers read: the system works, one line per supplier.
  await expect(flow.locator('.rf-readers')).toBeVisible()
  await expect(flow).toHaveAttribute('data-actor', 'system')
  await expect(flow.locator('.flow-steps .flow-actor')).toHaveText('系统在做')
  // The comparison names the suppliers and says what the button buys.
  const best = flow.locator('[data-recovery-option="B"]')
  await expect(best).toContainText('百川批发', { timeout: 20000 })
  await expect(best).toContainText('推荐')
  await expect(best).toHaveAttribute('aria-checked', 'true')
  await expect(flow.locator('[data-recovery-option="C"]')).toContainText('不配送到门店所在区域')
  await expect(flow.locator('.flow-steps .flow-actor')).toHaveText('等你')
  // 63 units against 20 in stock: 40 would still leave 3 short, so 50 is the recommendation.
  await expect(next(page)).toHaveText('用百川批发补 50 件')
  await expect(flow.locator('.rf-title')).toHaveText('百川批发补 50 件最合适')
  await expect(flow.locator('.rf-sub')).toHaveText('7 天缺货 43 → 0 件 · 花 ¥475')
  // Another supplier and another quantity change the button, not the recommendation.
  await flow.locator('[data-recovery-option="A"]').click()
  await expect(next(page)).toHaveText('用安和商贸补 50 件')
  await flow
    .getByRole('group', { name: '安和商贸的数量' })
    .getByRole('button', { name: '60 件' })
    .click()
  await expect(next(page)).toHaveText('用安和商贸补 60 件')
  await expect(best).toContainText('推荐')
  expect(writes(m).some((p) => p.endsWith('/materialize') || p.endsWith('/decision'))).toBe(false)
})

test('采用与确认合并；之后发单、登记回复、登记到货，最后收成一行结果', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toComparison(page)
  await next(page).click()
  // One click: the plan is written and the approval dialog opens with the supplier's name.
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('核对这笔采购')
  await expect(dialog).toContainText('百川批发')
  expect(writes(m).at(-1)).toBe('operations-cases/case-one/materialize')
  expect(writes(m).some((p) => p.endsWith('/decision'))).toBe(false)
  await dialog.getByRole('button', { name: '确认采购 40 件 · ¥380' }).click()

  // Order sent by hand: the card moves on at once (the order is found by its plan before the
  // Case is read again), holds the order, and the plan slot does not repeat it.
  await expect(flow).toHaveAttribute('data-stage', 'order', { timeout: 2000 })
  await expect(page.locator('.task-result-column .primary:visible')).toHaveCount(1)
  await expect(flow.locator('.flow-step[aria-current="step"]')).toContainText('发单并登记回复')
  await expect(flow.locator('.flow-steps .flow-actor')).toHaveText('等你')
  await expect(flow.locator('.rf-title')).toHaveText('把订单发给百川批发，收到回复后贴回来')
  await expect(flow.locator('[data-order-message]')).toContainText('PO-1A2B3C4D')
  await expect(page.locator('[data-assisted-order]')).toHaveCount(0)
  await expect(page.locator('.space-workspace .tag[role="status"]').first()).toHaveText(
    '待供应商确认',
  )
  await expect(page.locator('.space-orders')).toContainText('百川批发')

  await flow.locator('[data-supplier-reply]').fill('收到，40件没问题，周四送到')
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'receive')
  await expect(flow.locator('.flow-step[aria-current="step"]')).toContainText('登记到货')
  await expect(flow.locator('.rf-title')).toHaveText('百川批发已确认 40 件，货到后请登记')
  await expect(page.locator('.space-workspace .tag[role="status"]').first()).toHaveText(
    '货到后请登记',
  )
  await expect(page.locator('.space-orders')).toContainText('货到后请登记')
  await expect(page.locator('[data-arrival-card]')).toHaveCount(0)

  await flow.locator('[data-record-arrival]').click()
  await expect(flow).toHaveAttribute('data-stage', 'summary')
  const summary = flow.locator('[data-recovery-summary]')
  await expect(summary).toContainText('应急补货完成')
  await expect(summary).toContainText('百川批发 40 件已到货')
  await expect(summary).toContainText('预计缺货 40 → 0 件')
  await expect(summary).toContainText('花了 ¥380')
  await expect(page.locator('[data-recovery-entry]')).toBeVisible()
  // The summary opens on demand and shows the full result.
  await summary.click()
  await expect(flow).toHaveAttribute('data-stage', 'result')
  await expect(flow.locator('.rf-title')).toHaveText('应急补货完成')
  expect(m.writes.find((w) => w.path.endsWith('/arrival'))!.body).toEqual({ quantity: 40 })
})

test('只有操作权限：采用后不弹确认，等有审批权限的人确认', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true, roles: ['operator'] })
  const flow = flowCard(page)
  await toComparison(page)
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'confirm')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(flow.locator('.rf-title')).toHaveText('核对后确认：用百川批发补 40 件')
  // No disabled button: the card waits for someone who may approve, and says so in its place.
  await expect(flow.locator('[data-recovery-waiting]')).toHaveText('等有审批权限的人确认')
  await expect(next(page)).toHaveCount(0)
  await expect(flow).toHaveAttribute('data-actor', 'other')
  await expect(flow.locator('.flow-steps .flow-actor')).toHaveText('等审批')
  expect(writes(m).some((p) => p.endsWith('/decision'))).toBe(false)
})

test('没有操作权限或后端没有恢复能力时，页头不出现应急补货', async ({ page }) => {
  await setupRecovery(page, { roles: ['approver'] })
  await expect(page.locator('.space-heading')).toBeVisible()
  await expect(page.locator('[data-recovery-entry]')).toHaveCount(0)
})

test('只给一部分：先按对方数量成交，缺的在同一事项里找别家补上', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('可以，但只有10件')
  await next(page).click()
  await expect(flow.locator('.rf-title')).toHaveText('百川批发只能给 10 件，订单是 40 件')
  await expect(flow).toHaveAttribute('data-stage', 'order')
  await expect(next(page)).toHaveText('按对方数量成交（10 件）')
  await expect(flow.locator('[data-recovery-switch]')).toHaveText('撤回整单，找别家补 40 件')
  await next(page).click()
  // Taken at 10: the rest is found elsewhere in this Case while those 10 are on their way.
  await expect(flow).toHaveAttribute('data-stage', 'compare')
  await expect(flow.locator('.rf-title')).toHaveText('百川批发只确认了 10 件')
  await expect(flow.locator('.rf-sub')).toHaveText('已按 10 件成交 · 还缺 30 件')
  await expect(next(page)).toHaveText('缺的找别家补上')
  // The 10 taken are recorded in the card, not on the page's arrival card: there recording them
  // would end the restock before the rest is found.
  await expect(page.locator('[data-arrival-card]')).toHaveCount(0)
  await expect(flow.locator('.rf-purchase[data-purchase="action-one"]')).toContainText(
    '百川批发 10 件',
  )
  await expect(page.locator('.task-result-column .primary:visible')).toHaveCount(1)
  await expect(page.locator('.space-order-list')).toContainText('10 件 · ¥95')
  await expect(page.locator('.space-order-list')).toContainText('订单 40 件')
  await next(page).click()
  await expect(flow.locator('[data-recovery-option="A"]')).toBeVisible()
  await expect(flow.locator('[data-recovery-option="B"]')).toHaveCount(0)
  expect(writes(m)).toContain('actions/action-one/partial-acceptance')
  const revision = m.writes.filter((w) => w.path.endsWith('/revise')).at(-1)!
  expect(revision.body.supplier_ids).not.toContain('B')
  expect(m.writes.filter((w) => w.path === 'operations-cases')).toHaveLength(1)
})

test('只给一部分时也可以撤回整单，在同一事项里排除这家重新比价', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('可以，但只有10件')
  await next(page).click()
  await flow.locator('[data-recovery-switch]').click()
  await expect(flow).toHaveAttribute('data-stage', 'compare')
  await expect(flow.locator('[data-recovery-option="A"]')).toBeVisible()
  await expect(flow.locator('[data-recovery-option="B"]')).toHaveCount(0)
  await expect(next(page)).toHaveText('用安和商贸补 40 件')
  expect(writes(m)).toContain('actions/action-one/withdrawal')
  const revision = m.writes.filter((w) => w.path.endsWith('/revise')).at(-1)!
  expect(revision.body.supplier_ids).not.toContain('B')
  expect(revision.body.supplier_ids).toContain('A')
})

test('拒单：预留资金释放，一键不找这家重新比价', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('抱歉，这批没货了')
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'compare')
  await expect(flow.locator('.rf-title')).toHaveText('百川批发拒单了')
  await expect(flow.locator('.rf-sub')).toHaveText('预留的 ¥380 已退回 · 还缺 40 件')
  await expect(next(page)).toHaveText('不找百川批发，重新比价')
  await next(page).click()
  await expect(flow.locator('[data-recovery-option="A"]')).toBeVisible()
  await expect(flow.locator('[data-recovery-option="B"]')).toHaveCount(0)
  const revision = m.writes.filter((w) => w.path.endsWith('/revise')).at(-1)!
  expect(revision.body.supplier_ids).not.toContain('B')
  // The regenerated settlement days follow the clock again.
  expect(revision.body.daily_demand).toHaveLength(7)
})

test('等原订单：进度换成等原订单到货，原订单到了给出结果', async ({ page }) => {
  const m = await setupRecovery(page, {
    prepare: (f, mock) => {
      // An original order of 50 units arrives in two days; the regular offer has expired.
      f.inbounds.items = [
        {
          action_id: 'original-order',
          mission_id: mock.mission.id,
          sku_id: mock.sku,
          external_order_id: 'ORIG-1',
          ordered_quantity: 50,
          received_quantity: 0,
          remaining_quantity: 50,
          expected_arrival_at: new Date(mock.clock() + 2 * DAY).toISOString(),
          arrival_status: 'NOT_RECEIVED',
          is_overdue: false,
        },
      ]
      f.dashboard.state.stocks[0].in_transit = 50
    },
  })
  const flow = flowCard(page)
  await page.locator('[data-recovery-entry]').click()
  // No gap over the seven days: closing is the main action, comparing anyway steps back.
  await expect(next(page)).toHaveText('关闭')
  await flow.locator('[data-recovery-start]').click()
  await expect(flow.locator('[data-recovery-option="wait"]')).toContainText('等原订单')
  await expect(flow.locator('[data-recovery-option="wait"]')).toHaveAttribute(
    'aria-checked',
    'true',
  )
  await expect(flow.locator('.rf-title')).toHaveText('等原订单就够：7 天内不缺货。')
  await expect(next(page)).toHaveText('就等原订单')
  await next(page).click()
  expect(m.writes.at(-1)!.body).toMatchObject({ operation: 'adopt_waiting' })
  await expect(flow).toHaveAttribute('data-stage', 'receive')
  await expect(flow.locator('.flow-step[aria-current="step"]')).toContainText('等原订单到货')
  await expect(flow.locator('.flow-step').nth(2)).toContainText('决定等原订单')
  await expect(flow.locator('.flow-steps .flow-actor')).toHaveText('系统在做')
  await expect(flow.locator('.rf-originals')).toContainText('原订单 50 件')
  // The original order arrives (the simulator reports it): the restock is over.
  const inbound = m.f.inbounds.items[0]
  Object.assign(inbound, {
    received_quantity: 50,
    remaining_quantity: 0,
    arrival_status: 'RECEIVED',
  })
  await expect(flow).toHaveAttribute('data-stage', 'summary', { timeout: 15000 })
  await expect(flow.locator('[data-recovery-summary]')).toContainText('已等到原订单')
  await expect(flow.locator('[data-recovery-summary]')).toContainText('原订单 50 件已到')
})

test('今日页：常规方案补不上缺口时给出找别家补，打开事项页即是说明', async ({ page }) => {
  const m = await setupRecovery(page, { entry: 'today', documents: true })
  const prompt = page.locator('[data-recovery-prompt]')
  await expect(prompt).toContainText('缺货风险')
  // The same gap the brief then names: seven days without a new purchase.
  await expect(prompt.locator('h2')).toHaveText('常规方案补不上缺口：不补的话 7 天缺 40 件')
  await prompt.getByRole('button', { name: '找别家补' }).click()
  await expect(page.locator('.space-workspace.task-workspace')).toBeVisible()
  await expect(flowCard(page)).toHaveAttribute('data-stage', 'brief')
  await expect(flowCard(page).locator('.rf-title')).toHaveText(
    `预计缺货：不补的话 ${dayLabel(m.clock() + 3 * DAY - 1000)} 起缺货，7 天共缺 40 件。`,
  )
  expect(writes(m)).toContain(`missions/${m.mission.id}/work-item`)
})

test('提醒卡：缺货提醒里找别家补，事项页打开说明', async ({ page }) => {
  await setupRecovery(page, { entry: 'today', documents: true })
  await page.getByRole('button', { name: /项经营提醒/ }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('预计缺货风险')
  await dialog.locator('[data-recovery-from-alert]').click()
  await expect(flowCard(page)).toHaveAttribute('data-stage', 'brief')
  await expect(flowCard(page).locator('.rf-title')).toContainText('预计缺货')
})

test('订单卡：被拒的采购在采购行给出找别家补，说明里排除这家', async ({ page }) => {
  const m = await setupRecovery(page, {
    documents: true,
    prepare: (f, mock) => {
      f.actions.items = [
        {
          id: 'declined-order',
          mission_id: mock.mission.id,
          plan_id: f.plan.id,
          approval_id: 'approval-old',
          status: 'FAILED',
          channel: 'assisted',
          quantity: 30,
          amount_minor: 28500,
          currency: 'CNY',
          external_order_id: null,
          receipt: null,
          last_error: 'Supplier declined in the pasted reply',
          order_message: null,
          supplier_reply: {
            text: '抱歉没货',
            read_by: 'rules',
            outcome: 'declined',
            decision: 'rejected',
            quantity: null,
            unit_price_minor: null,
            total_minor: null,
            delivery_date: null,
            supplier_order_ref: null,
            quotes: {},
            differences: [],
            recorded_at: '2026-10-02T00:00:00Z',
            recorded_by: 'test-owner',
          },
          created_at: '2026-10-02T00:00:00Z',
          updated_at: '2026-10-02T00:00:00Z',
          purchase_snapshot: { ...f.plan.proposed_purchase, supplier_id: 'B', quantity: 30 },
        },
      ]
    },
  })
  const link = page.locator('[data-recovery-from-order]')
  await expect(link).toHaveText('找别家补')
  await link.click()
  const flow = flowCard(page)
  await expect(flow).toHaveAttribute('data-stage', 'brief')
  await expect(flow.locator('.rf-title')).toContainText('百川批发拒单，找别家补上')
  await next(page).click()
  // The declined supplier is left out once the reviewers have read it again.
  await expect(flow.locator('[data-recovery-option="A"]')).toBeVisible({ timeout: 20000 })
  await expect(flow.locator('[data-recovery-option="B"]')).toHaveCount(0)
  const created = m.writes.find((w) => w.path === 'operations-cases')!
  expect(created.body.supplier_ids).not.toContain('B')
})

test('比价过期：主按钮变成重新比价，按当前时钟重排需求', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  await toComparison(page)
  m.item.stale = true
  m.item.proposal.expires_at = new Date(Date.now() - 1000).toISOString()
  await expect(next(page)).toHaveText('重新比价', { timeout: 10000 })
  // One cause, the one that holds: the comparison ran out (not "or the data changed").
  await expect(flowCard(page).locator('.rf-title')).toHaveText('比价结果需要更新')
  await expect(flowCard(page).locator('.rf-sub')).toHaveText('比价结果已超过有效期。')
  await next(page).click()
  await expect(next(page)).toHaveText('用百川批发补 40 件')
  expect(writes(m).slice(-2)).toEqual([
    'operations-cases/case-one/revise',
    'operations-cases/case-one/analyze',
  ])
})

test('提交结果不明：卡片写明哪一步还没确认，再试一次沿用原来的幂等键', async ({ page }) => {
  const m = await setupRecovery(page, {
    documents: true,
    prepare: (_f, mock) => mock.loseReply.push('materialize'),
  })
  const flow = flowCard(page)
  await toComparison(page)
  // The adoption takes effect, but its answer is lost on the way back.
  await next(page).click()
  await expect(flow.locator('[data-recovery-unconfirmed]')).toBeVisible()
  await expect(flow.locator('.rf-title')).toHaveText('采用这份报价的结果还没确认')
  await expect(flow).toHaveAttribute('data-actor', 'you')
  await expect(next(page)).toHaveText('再试一次（沿用刚才的提交）')
  // Nothing else writes meanwhile: the header has no way into a second restock either.
  await expect(page.locator('[data-recovery-entry]')).toHaveCount(0)
  await next(page).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  const sent = m.writes.filter((w: any) => w.path.endsWith('/materialize'))
  expect(sent).toHaveLength(2)
  expect(sent[1].key).toBe(sent[0].key)
})

test('委托记录：应急补货期间后端写的检查结果显示为中文', async ({ page }) => {
  const at = new Date().toISOString()
  await setupRecovery(page, {
    prepare: (f) =>
      f.timeline.items.push(
        {
          id: 'check-one',
          type: 'CHECK_COMPLETED',
          summary: '检查SKIPPED：Recovery plan awaits explicit approval（任务job-one）',
          actor_type: 'SYSTEM',
          references: [],
          created_at: at,
        },
        {
          id: 'check-two',
          type: 'CHECK_COMPLETED',
          summary: '检查INCONCLUSIVE：FORECAST_UNAVAILABLE（任务job-two）',
          actor_type: 'SYSTEM',
          references: [],
          created_at: at,
        },
      ),
  })
  const records = page.locator('.space-timeline')
  await expect(records).toContainText('检查完成：应急方案等你确认，本次跳过')
  await expect(records).toContainText('检查完成：需求预测暂不可用，未能检查')
  await expect(records).not.toContainText('Recovery plan')
})

test('报价全部过期：主按钮变成重新找货，重新读资料后可以再比较', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  await toComparison(page)
  // Every quote on file has run out since the comparison was made.
  for (const offer of m.f.catalog.offers)
    offer.valid_until = new Date(Date.now() - 1000).toISOString()
  m.analyze()
  await expect(next(page)).toHaveText('重新找货')
  await next(page).click()
  await expect(next(page)).toHaveText('用百川批发补 40 件', { timeout: 30000 })
  expect(writes(m).some((path) => path.endsWith('/source'))).toBe(true)
})

test('采用后方案失效：卡片写明后端给的原因，主按钮重新比价', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true, roles: ['operator'] })
  const flow = flowCard(page)
  await toComparison(page)
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'confirm')
  // Nobody confirmed it in time (planning/jobs.py): the Case asks for a new comparison.
  m.plans[m.item.plan_id].status = 'EXPIRED'
  m.item.plan_status = 'EXPIRED'
  m.item.status = 'RECHECK_REQUIRED'
  m.item.recheck_reason = 'PLAN_EXPIRED'
  await expect(flow.locator('.rf-title')).toHaveText('应急方案已过期')
  await expect(flow.locator('.rf-sub')).toHaveText('重新比价后再确认')
  await expect(next(page)).toHaveText('重新比价')
  await expect(page.locator('[data-regular-plan-line]')).toHaveCount(0)
})

test('拒绝应急方案：事项继续占着、例行检查暂停，可以重新比价或结束', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true, roles: ['operator'] })
  const flow = flowCard(page)
  await toComparison(page)
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'confirm')
  // Someone who may approve turned it down (operations_cases/lifecycle.py rejected()).
  m.plans[m.item.plan_id].status = 'REJECTED'
  m.f.plan.status = 'REJECTED'
  m.item.plan_status = 'REJECTED'
  await expect(flow.locator('.rf-title')).toHaveText('你没有采用这份应急方案')
  await expect(flow.locator('.rf-sub')).toHaveText('结束这次应急补货后，系统才恢复每天的补货建议')
  await expect(next(page)).toHaveText('重新比价')
  await expect(flow.getByRole('button', { name: '结束这次应急补货' })).toBeVisible()
})

test('供应商名称以字母或数字结尾时，与中文之间留一个空格', async ({ page }) => {
  await setupRecovery(page, {
    documents: true,
    prepare: (_f, m) => (m.documents[1].name = 'Metro'),
  })
  await toComparison(page)
  await expect(next(page)).toHaveText('用 Metro 补 40 件')
  await expect(flowCard(page).locator('.rf-title')).toHaveText('Metro 补 40 件最合适')
  await expect(flowCard(page).locator('.rf-sub')).toHaveText('7 天缺货 40 → 0 件 · 花 ¥380')
  await expect(flowCard(page).locator('[data-recovery-option="A"]')).toContainText('安和商贸')
})

test('英文界面：入口、进度与按钮都有英文', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('shopsteward.locale.v1', 'en'))
  await setupRecovery(page, { documents: true })
  await page.locator('[data-recovery-entry]').click()
  const flow = flowCard(page)
  await expect(page.locator('[data-recovery-entry]')).toHaveCount(0)
  await expect(flow.locator('.rf-eyebrow')).toHaveText('Emergency restock')
  await expect(flow.locator('.flow-step[aria-current="step"] .flow-label')).toContainText(
    'Describe',
  )
  await expect(flow.locator('.flow-steps .flow-actor')).toHaveText('Your turn')
  await expect(flow.locator('[data-fact="demand"] b')).toHaveText('60 units')
  await expect(next(page)).toHaveText('Confirm and find suppliers')
  await next(page).click()
  await expect(flow.locator('[data-recovery-option="B"]')).toBeVisible({ timeout: 20000 })
  await expect(next(page)).toHaveText('Restock 40 units from 百川批发')
  await expect(flow).not.toContainText('等你')
})

test('一屏一个主按钮：应急补货进行中，可确认的常规方案收成一行', async ({ page }) => {
  await setupRecovery(page, { documents: true })
  await expect(page.locator('.space-plan-card')).toBeVisible()
  await toComparison(page)
  const column = page.locator('.task-result-column')
  await expect(column.locator('[data-regular-plan-line]')).toContainText(
    '常规方案：建议补 20 件 · ¥200',
  )
  await expect(page.locator('.space-plan-card')).toHaveCount(0)
  await expect(column.locator('.primary:visible')).toHaveCount(1)
  // The line still reaches the regular plan's own confirmation.
  await column.locator('[data-regular-plan-line]').getByRole('button').click()
  await expect(page.getByRole('dialog')).toContainText('核对这笔采购')
})

test('键盘：比较是一个单选组，方向键移动选择，回车打开确认', async ({ page }) => {
  await setupRecovery(page, { documents: true })
  await toComparison(page)
  const flow = flowCard(page)
  const recommended = flow.locator('[data-recovery-option="B"]')
  await expect(recommended).toHaveAttribute('tabindex', '0')
  await expect(flow.locator('[data-recovery-option="A"]')).toHaveAttribute('tabindex', '-1')
  await recommended.focus()
  await page.keyboard.press('ArrowDown')
  await expect(flow.locator('[data-recovery-option="A"]')).toBeFocused()
  await expect(flow.locator('[data-recovery-option="A"]')).toHaveAttribute('aria-checked', 'true')
  await expect(next(page)).toHaveText('用安和商贸补 40 件')
  await page.keyboard.press('ArrowDown')
  await expect(flow.locator('[data-recovery-option="wait"]')).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(recommended).toBeFocused()
  await expect(next(page)).toHaveText('用百川批发补 40 件')
  await next(page).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog')).toContainText('核对这笔采购')
})

test('这次不补：没有原订单时停在这一步，如实说明，结束后例行检查恢复', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toComparison(page)
  await flow.locator('[data-recovery-option="wait"]').click()
  await expect(next(page)).toHaveText('这次不补')
  await next(page).click()
  expect(m.writes.at(-1)!.body).toMatchObject({ operation: 'adopt_waiting' })
  // The backend holds such a Case open (routine checks paused) until the owner ends it.
  await expect(flow).toHaveAttribute('data-stage', 'receive')
  await expect(flow.locator('.flow-step[aria-current="step"]')).toContainText('决定这次不补')
  await expect(flow.locator('.rf-title')).toHaveText('这次不补')
  await expect(flow.locator('.rf-sub')).toHaveText(
    '没有在途的原订单。结束后，系统恢复每天的补货建议。',
  )
  await expect(next(page)).toHaveText('结束这次应急补货')
  await next(page).click()
  expect(m.writes.at(-1)!.body).toMatchObject({ operation: 'cancel' })
  await expect(flow.locator('[data-recovery-summary]')).toContainText('应急补货已结束')
})

test.describe('手机 390 宽', () => {
  test.use({ viewport: { width: 390, height: 844 } })
  test('每个阶段都没有横向溢出，进度只显示当前一段', async ({ page }) => {
    await setupRecovery(page, { documents: true })
    const flow = flowCard(page)
    const fits = async (stage: string) => {
      await expect(flow).toBeVisible()
      const width = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ])
      expect(width[0], `横向溢出：${stage}`).toBeLessThanOrEqual(width[1]!)
      const box = (await flow.boundingBox())!
      expect(box.x + box.width, `卡片超出屏幕：${stage}`).toBeLessThanOrEqual(390)
    }
    await page.locator('[data-recovery-entry]').click()
    await expect(flow.locator('.flow-compact')).toContainText('第 1/6 步')
    await expect(flow.locator('.flow-label').first()).toBeHidden()
    await fits('说明情况')
    await next(page).click()
    await expect(flow.locator('.rf-readers')).toBeVisible()
    await fits('读资料')
    await expect(flow.locator('[data-recovery-option="B"]')).toBeVisible({ timeout: 20000 })
    await fits('比较')
    await next(page).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await fits('确认弹窗')
    await page
      .getByRole('dialog')
      .getByRole('button', { name: /^确认采购/ })
      .click()
    await expect(flow).toHaveAttribute('data-stage', 'order')
    await fits('发单')
    await flow.locator('[data-supplier-reply]').fill('可以，但只有10件')
    await next(page).click()
    await expect(flow.locator('[data-recovery-switch]')).toBeVisible()
    await fits('只给一部分')
    await flow.locator('[data-recovery-new-reply]').click()
    await flow.locator('[data-supplier-reply]').fill('收到，40件没问题')
    await flow.locator('[data-recovery-submit-reply]').click()
    await expect(flow).toHaveAttribute('data-stage', 'receive')
    await fits('登记到货')
    await flow.locator('[data-record-arrival]').click()
    await expect(flow).toHaveAttribute('data-stage', 'summary')
    await fits('结果')
  })
})

test('分析失败：卡片说明原因，一键重新比价，不会停在“正在比价”', async ({ page }) => {
  const m = await setupRecovery(page, { prepare: (_f, mock) => (mock.failAnalyze = 1) })
  const flow = flowCard(page)
  await page.locator('[data-recovery-entry]').click()
  await next(page).click()
  await expect(flow.locator('.rf-title')).toHaveText('还没有比价结果')
  await expect(flow.locator('.rf-sub')).toHaveCount(0)
  await expect(flow).toContainText('数据还未同步完成')
  await expect(flow).toHaveAttribute('data-actor', 'you')
  await expect(next(page)).toHaveText('重新比价')
  await next(page).click()
  await expect(flow.locator('[data-recovery-option="wait"]')).toBeVisible()
  expect(writes(m).slice(-2)).toEqual([
    'operations-cases/case-one/revise',
    'operations-cases/case-one/analyze',
  ])
})

/** From the partial reply to "缺的找别家补上": 百川批发 gives 10 of 40, taken at 10. */
async function toShort(page: Page) {
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('可以，但只有10件')
  await next(page).click()
  await expect(next(page)).toHaveText('按对方数量成交（10 件）')
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'compare')
  await expect(next(page)).toHaveText('缺的找别家补上')
}

test('部分成交后采用第二家：两笔都到齐才结算，到货只在卡片里登记', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toShort(page)
  await next(page).click()
  await expect(flow.locator('[data-recovery-option="A"]')).toBeVisible()
  await expect(flow.locator('[data-recovery-option="B"]')).toHaveCount(0)
  await next(page).click()
  await page
    .getByRole('dialog')
    .getByRole('button', { name: /^确认采购 \d+ 件/ })
    .click()
  await expect(flow).toHaveAttribute('data-stage', 'order')
  const second = m.f.actions.items[0]
  expect(second.id).toBe('action-two')
  expect(second.purchase_snapshot.supplier_id).toBe('A')
  await flow.locator('[data-supplier-reply]').fill(`收到，${second.quantity}件没问题`)
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'receive')
  await expect(flow).toHaveAttribute('data-actor', 'you')
  await expect(page.locator('[data-arrival-card]')).toHaveCount(0)
  // The second supplier's goods are all in, the first one's 10 are not: nothing settles yet,
  // and the card does not claim it is settling.
  await flow.locator('[data-record-arrival]').click()
  await expect(flow.locator('[data-purchase="action-one"]')).toBeVisible()
  await expect(flow).toHaveAttribute('data-stage', 'receive')
  await expect(flow).toHaveAttribute('data-actor', 'you')
  expect(m.item.status).toBe('MONITORING')
  // The last 10 are in: the backend settles the Case with both purchases.
  await flow.locator('[data-purchase="action-one"] [data-purchase-record]').click()
  await expect(flow.locator('[data-purchase="action-one"] .rf-consequence')).toHaveCount(0)
  await flow.locator('[data-purchase="action-one"] [data-purchase-arrival]').click()
  await expect(flow).toHaveAttribute('data-stage', 'summary')
  expect(m.item.status).toBe('RESOLVED')
  expect(m.item.outcome.action_ids).toEqual(['action-one', 'action-two'])
  // The result adds the units up per supplier; the orders' own total (40 + the second) is not it.
  await expect(flow.locator('[data-recovery-summary]')).toContainText(
    `补到 ${10 + second.quantity} 件（百川批发 10 + 安和商贸 ${second.quantity}）`,
  )
  const arrivals = m.writes.filter((w) => w.path.endsWith('/arrival'))
  expect(arrivals.map((w) => w.path)).toEqual([
    'actions/action-two/arrival',
    'actions/action-one/arrival',
  ])
})

test('部分成交阶段登记那几件到货：先说明会结束这次应急补货，再登记', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toShort(page)
  // Not offered on the page's arrival card; in the card, the consequence comes first.
  await expect(page.locator('[data-arrival-card]')).toHaveCount(0)
  const row = flow.locator('[data-purchase="action-one"]')
  await row.locator('[data-purchase-record]').click()
  await expect(row.locator('.rf-consequence')).toBeVisible()
  expect(writes(m).some((p) => p.endsWith('/arrival'))).toBe(false)
  await row.locator('[data-purchase-arrival]').click()
  // As said: with everything bought in, the backend settles the Case at 10.
  await expect(flow).toHaveAttribute('data-stage', 'summary')
  expect(m.item.status).toBe('RESOLVED')
  expect(m.item.outcome).toMatchObject({ purchased_qty: 10, planned_qty: 40 })
})

test('两次拒单：两家都不再出现在比较里', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('抱歉，这批没货了')
  await next(page).click()
  await expect(next(page)).toHaveText('不找百川批发，重新比价')
  await next(page).click()
  await flow.locator('[data-recovery-option="A"]').click()
  await expect(next(page)).toHaveText(/^用安和商贸补 \d+ 件$/)
  await next(page).click()
  await page
    .getByRole('dialog')
    .getByRole('button', { name: /^确认采购 \d+ 件/ })
    .click()
  await expect(flow).toHaveAttribute('data-stage', 'order')
  await flow.locator('[data-supplier-reply]').fill('抱歉，没货')
  await next(page).click()
  await expect(next(page)).toHaveText('不找安和商贸，重新比价')
  await next(page).click()
  await expect(flow.locator('[data-recovery-option="A"]')).toHaveCount(0)
  await expect(flow.locator('[data-recovery-option="B"]')).toHaveCount(0)
  const revision = m.writes.filter((w) => w.path.endsWith('/revise')).at(-1)!
  expect(revision.body.supplier_ids).not.toContain('A')
  expect(revision.body.supplier_ids).not.toContain('B')
  const kept = await page.evaluate(() => sessionStorage.getItem('ss.recovery.excluded:case-one'))
  expect(JSON.parse(kept!)).toEqual(expect.arrayContaining(['A', 'B']))
})

test('一屏一个主按钮：应急方案待确认时经营状态变了不另出问题卡，数据没同步仍然说', async ({
  page,
}) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toComparison(page)
  await next(page).click()
  await page.getByRole('dialog').getByRole('button', { name: '关闭对话框' }).click()
  await expect(flow).toHaveAttribute('data-stage', 'confirm')
  // Stock or cash changed under the pending emergency plan: the card says it (its button
  // waits); no issue card adds a second primary.
  const column = page.locator('.task-result-column')
  m.f.dashboard.state.state_version++
  await page.waitForResponse((r) => r.url().includes('/dashboard'))
  await page.waitForResponse((r) => r.url().includes('/dashboard'))
  await expect(column.locator('.space-issue')).toHaveCount(0)
  await expect(column.locator('.primary:visible')).toHaveCount(1)
  m.plans[m.item.plan_id].status = 'EXPIRED'
  await page.waitForResponse((r) => r.url().includes('/plans/'))
  await page.waitForResponse((r) => r.url().includes('/dashboard'))
  await expect(column.locator('.space-issue')).toHaveCount(0)
  await expect(column.locator('.primary:visible')).toHaveCount(1)
  // Data that is not synced is about the whole store: still said, with a second button.
  m.f.dashboard.freshness.status = 'STALE'
  await expect(column.locator('.space-issue')).toBeVisible()
  await expect(column.locator('.primary:visible')).toHaveCount(1)
})

test('换一家后再采用：先按当前情况重新比价，再采用新选的那家', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toComparison(page)
  await next(page).click()
  await page.getByRole('dialog').getByRole('button', { name: '关闭对话框' }).click()
  await expect(flow).toHaveAttribute('data-stage', 'confirm')
  await flow.getByRole('button', { name: '换一家' }).click()
  await expect(flow).toHaveAttribute('data-stage', 'compare')
  await expect(flow.getByRole('button', { name: '不换了，回去确认' })).toBeVisible()
  await flow.locator('[data-recovery-option="A"]').click()
  await next(page).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('安和商贸')
  // Adopting raised the mission's version, so the comparison is made again before adopting.
  const sent = writes(m)
  const last = sent.lastIndexOf('operations-cases/case-one/materialize')
  expect(sent.slice(last - 2, last + 1)).toEqual([
    'operations-cases/case-one/revise',
    'operations-cases/case-one/analyze',
    'operations-cases/case-one/materialize',
  ])
  await dialog.getByRole('button', { name: /^确认采购 \d+ 件/ }).click()
  await expect(flow).toHaveAttribute('data-stage', 'order')
  expect(m.f.actions.items[0].purchase_snapshot.supplier_id).toBe('A')
})

test('登记到货生效但回音丢了：刷新后看到已入账，不会再记一次', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('收到，40件没问题')
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'receive')
  m.loseReply.push('arrival')
  await flow.locator('[data-record-arrival]').click()
  // The order now reads 40/40: the write took effect, so the restock settles as it should.
  await expect(flow).toHaveAttribute('data-stage', 'summary')
  expect(m.writes.filter((w) => w.path.endsWith('/arrival'))).toHaveLength(1)
  expect(m.f.inbounds.items.find((i: any) => i.action_id === 'action-one').received_quantity).toBe(
    40,
  )
})

test('采购没有执行（方案已失效）：卡片写明后端给的原因，主按钮重新比价', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  const order = m.f.actions.items[0]
  order.status = 'STALE'
  m.release(order)
  m.recheck(order, 'PURCHASE_STALE')
  await expect(flow).toHaveAttribute('data-stage', 'compare', { timeout: 10000 })
  await expect(flow).toContainText('原方案已失效，这笔采购没有执行。')
  await expect(next(page)).toHaveText('重新比价')
})

test('刷新之后：结果不明的建立仍待核实，核实沿用原来的幂等键', async ({ page }) => {
  const m = await setupRecovery(page, {
    documents: true,
    prepare: (_f, mock) => (mock.dropCreate = 1),
  })
  const flow = flowCard(page)
  await page.locator('[data-recovery-entry]').click()
  await next(page).click()
  await expect(flow.locator('[data-recovery-unconfirmed]')).toBeVisible()
  await page.reload()
  // No Case was read, yet the card says what waits to be verified; no second restock starts.
  await expect(flow.locator('[data-recovery-unconfirmed]')).toBeVisible()
  await expect(page.locator('[data-recovery-entry]')).toHaveCount(0)
  await next(page).click()
  await expect(flow.locator('[data-recovery-option="B"]')).toBeVisible({ timeout: 20000 })
  const created = m.writes.filter((w) => w.path === 'operations-cases')
  expect(created).toHaveLength(2)
  expect(created[1]!.key).toBe(created[0]!.key)
})

test('登记到货没有回音：再登记沿用原来的幂等键，不重复入账', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('收到，40件没问题')
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'receive')
  // The first attempt never reached the books; the second goes out under the same key.
  m.dropWrite.push('arrival')
  await flow.locator('[data-record-arrival]').click()
  await expect(flow).toHaveAttribute('data-stage', 'receive')
  await flow.locator('[data-record-arrival]').click()
  await expect(flow).toHaveAttribute('data-stage', 'summary')
  const sent = m.writes.filter((w) => w.path.endsWith('/arrival'))
  expect(sent).toHaveLength(2)
  expect(sent[1]!.key).toBe(sent[0]!.key)
  expect(m.f.inbounds.items.find((i: any) => i.action_id === 'action-one').received_quantity).toBe(
    40,
  )
})

test('响应乱序：采用之后才回来的旧读取不会把卡片拉回比较', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true, roles: ['operator'] })
  const flow = flowCard(page)
  await toComparison(page)
  // A read of the Case asked before adopting answers only after the adoption is written.
  m.holdRead = true
  await expect.poll(() => !!m.releaseRead, { timeout: 10000 }).toBe(true)
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'confirm')
  m.releaseRead!()
  await page.waitForTimeout(600)
  await expect(flow).toHaveAttribute('data-stage', 'confirm')
})
