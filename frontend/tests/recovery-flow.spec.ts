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
  await expect(flow.locator('[data-fact="demand"] b')).toHaveText('7 天共 60 件')
  await expect(flow.locator('[data-fact="demand"] small')).toHaveText('按当前需求假设')
  await expect(flow.locator('[data-fact="settlement"] b')).toHaveText(
    settlement(clock + DAY - 1000),
  )
  await expect(flow.locator('[data-fact="documents"] b')).toHaveText('3 家')
  expect(writes(m)).toContain(`stores/${m.store}/supplier-documents/sample`)
  // Quick fill: a flat daily demand.
  await flow.getByRole('button', { name: '每天 9 件' }).click()
  await expect(flow.locator('[data-fact="demand"] b')).toHaveText('7 天共 63 件')
  await expect(flow.locator('[data-fact="demand"] small')).toHaveText('按你填的每天件数')
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
  await expect(flow.locator('.rf-title')).toHaveText(
    '百川批发补 50 件最合适：7 天缺货从 43 件降到 0 件，花 ¥475。',
  )
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

  // Order sent by hand: the flow holds the order, the plan slot is not repeated.
  await expect(flow).toHaveAttribute('data-stage', 'order')
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
  await expect(flow).toContainText('确认采购需要审批权限')
  // 百川批发 is known only from its documents, so the backend leaves the order to the owner.
  await expect(flow).toContainText('确认后由你把订单发给供应商')
  await expect(next(page)).toBeDisabled()
  expect(writes(m).some((p) => p.endsWith('/decision'))).toBe(false)
})

test('没有操作权限或后端没有恢复能力时，页头不出现应急补货', async ({ page }) => {
  await setupRecovery(page, { roles: ['approver'] })
  await expect(page.locator('.space-heading')).toBeVisible()
  await expect(page.locator('[data-recovery-entry]')).toHaveCount(0)
})

test('只给一部分：撤回整单，在同一事项里排除这家重新比价', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('可以，但只有10件')
  await next(page).click()
  await expect(flow.locator('.rf-title')).toHaveText('百川批发只能给 10 件，订单是 40 件')
  await expect(flow).toHaveAttribute('data-stage', 'order')
  await expect(next(page)).toHaveText('撤回这单，找别家补 40 件')
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'compare')
  await expect(flow.locator('[data-recovery-option="A"]')).toBeVisible()
  await expect(flow.locator('[data-recovery-option="B"]')).toHaveCount(0)
  await expect(next(page)).toHaveText('用安和商贸补 40 件')
  const order = writes(m)
  expect(order).toContain('actions/action-one/withdrawal')
  const revision = m.writes.filter((w) => w.path.endsWith('/revise')).at(-1)!
  expect(revision.body.supplier_ids).not.toContain('B')
  expect(revision.body.supplier_ids).toContain('A')
  expect(m.writes.filter((w) => w.path === 'operations-cases')).toHaveLength(1)
})

test('拒单：预留资金释放，一键不找这家重新比价', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toOrder(page)
  await flow.locator('[data-supplier-reply]').fill('抱歉，这批没货了')
  await next(page).click()
  await expect(flow).toHaveAttribute('data-stage', 'compare')
  await expect(flow.locator('.rf-banner')).toHaveText('百川批发拒单，预留资金已释放。')
  await expect(flow.locator('.rf-title')).toHaveText('找别家补上这个缺口')
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
  await next(page).click()
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
  await expect(prompt.locator('h2')).toHaveText('按常规方案补完仍会缺货：7 天预计缺 20 件')
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
  await expect(next(page)).toHaveText('重新比价', { timeout: 10000 })
  await expect(flowCard(page).locator('.rf-banner')).toContainText('比价结果已超过有效期')
  await next(page).click()
  await expect(next(page)).toHaveText('用百川批发补 40 件')
  expect(writes(m).slice(-2)).toEqual([
    'operations-cases/case-one/revise',
    'operations-cases/case-one/analyze',
  ])
})

test('提交结果不明：卡片写明哪一步还没确认，核实并重试原提交沿用原来的幂等键', async ({ page }) => {
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
  await expect(next(page)).toHaveText('核实并重试原提交')
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

test('应急方案被常规检查换掉：常规方案那一行写明已失效，在那一行就能重新比价', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const regular = structuredClone(m.f.plan)
  await toComparison(page)
  // The owner adopted 40 from 百川批发 earlier; a regular check has since replaced that plan.
  m.materialize('B_40')
  m.item.plan_status = 'SUPERSEDED'
  m.plans[m.item.plan_id].status = 'SUPERSEDED'
  m.f.plan = regular
  m.mission.current_plan_id = regular.id
  const flow = flowCard(page)
  const line = page.locator('[data-regular-plan-line]')
  await expect(flow.locator('.rf-banner')).toHaveText('待确认的应急方案被常规检查换掉了。')
  await expect(line).toContainText('应急方案已失效，现在是常规方案：建议补 20 件 · ¥200')
  await expect(page.locator('.task-result-column .primary:visible')).toHaveCount(1)
  await line.locator('[data-regular-plan-again]').click()
  await expect(flow.locator('[data-recovery-option="B"]')).toBeVisible()
  await expect(line).toHaveText(/^常规方案：建议补 20 件 · ¥200/)
  await expect(line.locator('[data-regular-plan-again]')).toHaveCount(0)
  expect(writes(m).slice(-2)).toEqual([
    'operations-cases/case-one/revise',
    'operations-cases/case-one/analyze',
  ])
})

test('供应商名称以字母或数字结尾时，与中文之间留一个空格', async ({ page }) => {
  await setupRecovery(page, {
    documents: true,
    prepare: (_f, m) => (m.documents[1].name = 'Metro'),
  })
  await toComparison(page)
  await expect(next(page)).toHaveText('用 Metro 补 40 件')
  await expect(flowCard(page).locator('.rf-title')).toHaveText(
    'Metro 补 40 件最合适：7 天缺货从 40 件降到 0 件，花 ¥380。',
  )
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
  await expect(flow.locator('[data-fact="demand"] b')).toHaveText('60 units over 7 days')
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

test('这次不补：没有原订单时，等待就是不补，结果写明', async ({ page }) => {
  const m = await setupRecovery(page, { documents: true })
  const flow = flowCard(page)
  await toComparison(page)
  await flow.locator('[data-recovery-option="wait"]').click()
  await expect(next(page)).toHaveText('这次不补')
  await next(page).click()
  expect(m.writes.at(-1)!.body).toMatchObject({ operation: 'adopt_waiting' })
  const summary = flow.locator('[data-recovery-summary]')
  await expect(summary).toContainText('应急补货已结束')
  await expect(summary).toContainText('这次不补')
  await expect(summary).toContainText('预计缺货 40 件')
  await summary.click()
  await expect(flow.locator('.flow-step').nth(2)).toContainText('决定这次不补')
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
    await flow.locator('[data-supplier-reply]').fill('收到，40件没问题')
    await flow.getByRole('button', { name: '登记新回复' }).click()
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
  await expect(flow.locator('.rf-title')).toHaveText('比价结果需要更新')
  await expect(flow.locator('.rf-banner')).toHaveText('还没有比价结果。')
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
