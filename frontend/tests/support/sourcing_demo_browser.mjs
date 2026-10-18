// Walks the sourcing and owner-sent purchase demo in a real browser against a running stack:
// real HTTP, database and models, no request interception. It creates a synthetic SC01 store.
// DEMO_FRONTEND must be a loopback URL; DEMO_OUTPUT, when set, receives screenshots and a record.
import { chromium, expect } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
const base = process.env.DEMO_FRONTEND
if (!base || new URL(base).hostname !== '127.0.0.1')
  throw Error('An explicit loopback demo URL is required')
const out = process.env.DEMO_OUTPUT
if (out) await mkdir(out, { recursive: true })
// The confirming reply is written from the order itself unless one is given.
const reply = process.env.DEMO_REPLY
const browser = await chromium.launch({ headless: process.env.DEMO_HEADED !== '1' })
const page = await browser.newPage({
  viewport: { width: 1440, height: 1100 },
  reducedMotion: 'reduce',
})
const errors = []
const steps = []
page.on('pageerror', (e) => errors.push(e.message))
const backend = base + '/api/backend'
const read = async (path) => {
  const response = await page.request.get(backend + path)
  expect(response.ok(), path + ' ' + (await response.text())).toBe(true)
  return response.json()
}
const write = async (path, data) => {
  const response = await page.request.post(backend + path, {
    data,
    headers: { 'Idempotency-Key': randomUUID() },
  })
  expect(response.ok(), path + ' ' + (await response.text())).toBe(true)
  return response.json()
}
const job = async (id) => {
  await expect
    .poll(async () => (await read('/api/v1/job-runs/' + id)).status, { timeout: 60000 })
    .toBe('SUCCEEDED')
  return read('/api/v1/job-runs/' + id)
}
let shot = 0
const step = async (name, facts = {}) => {
  steps.push({ step: name, ...facts })
  console.log('ok', name, JSON.stringify(facts))
  if (out)
    await page.screenshot({
      path: `${out}/${String(++shot).padStart(2, '0')}-${name}.png`,
      fullPage: true,
    })
}
const stockOf = async (store, sku) =>
  (await read('/api/v1/dashboard?store_id=' + store)).state.stocks.find((s) => s.sku_id === sku)
try {
  const identity = await (await page.request.get(base + '/api/session')).json()
  expect(identity.authenticated, 'the frontend needs a connected backend identity').toBe(true)
  expect(identity.sourcing, 'the backend must offer sourcing').toBe(true)

  // A fresh synthetic store with one replenishment mission; neither is what this walk checks.
  const created = await job((await write('/dev/v1/scenarios', { scenario: 'SC01' })).job_run_id)
  const store = created.result.references.find((r) => r.type === 'store').id
  const catalog = await read('/api/v1/catalog?store_id=' + store)
  const offer = catalog.offers[0]
  const sku = offer.sku_id
  const mission = await write('/api/v1/missions', {
    store_id: store,
    sku_id: sku,
    objective: '活动备货：尽量减少缺货，现金至少保留300元，采购逐笔确认。',
    policy: {
      cash_floor_minor: 30000,
      candidate_quantities: [0, 20, 40, 80],
      supplier_id: offer.supplier_id,
    },
    check_interval_seconds: 30,
  })
  const before = await stockOf(store, sku)
  // The owner works on the mission from its work item, as the today page opens it.
  const { item } = await write(`/api/v1/missions/${mission.id}/work-item`, {})
  await page.goto(`${base}/?view=work&store=${store}&item=${item.id}`)
  await expect(page.locator('.space-workspace')).toBeVisible({ timeout: 30000 })
  await expect(page.getByRole('button', { name: '供应异常应对', exact: true })).toBeVisible({
    timeout: 30000,
  })
  await step('work-item', { store, on_hand: before.on_hand, in_transit: before.in_transit })

  // 1. A recovery Case: seven days of demand the shelf cannot cover.
  await page.getByRole('button', { name: '供应异常应对', exact: true }).click()
  await page.getByLabel('本次应急预算（元）', { exact: true }).fill('300')
  await page.getByText('补充七日需求情景（没有可用日预测时填写）').click()
  await page.getByLabel('七日需求（件，逗号分隔）', { exact: true }).fill('10,10,10,10,10,10,10')
  const clock = new Date((await read('/api/v1/dashboard?store_id=' + store)).state.simulation_time)
  const first = new Date(clock.getTime() + 86400000 - 60000).toISOString().slice(0, 16)
  await page.getByLabel('首日结算时间（UTC）', { exact: true }).fill(first)
  await page.getByRole('button', { name: '开始分析', exact: true }).click()
  let detail
  await expect
    .poll(
      async () => {
        const list = await read('/api/v1/operations-cases?store_id=' + store)
        detail = list.items[0] && (await read('/api/v1/operations-cases/' + list.items[0].id))
        return detail?.status
      },
      { timeout: 60000 },
    )
    .toBe('OPTIONS_READY')
  const casePath = '/api/v1/operations-cases/' + detail.id
  await step('case-analysed', { case_id: detail.id, revision: detail.current_revision })

  // 2. Sourcing: one reviewer per supplier reads the sample documents.
  const panel = page.locator('[data-sourcing]')
  await panel.getByRole('button', { name: '载入三家供应商的示例资料', exact: true }).click()
  await expect(panel).toContainText('资料在档')
  await step('sample-documents-loaded')
  const started = Date.now()
  await panel.getByRole('button', { name: '开始寻源', exact: true }).click()
  await expect
    .poll(async () => (await read(casePath)).sourcing?.status, {
      timeout: 330000,
      intervals: [3000],
    })
    .toMatch(/^(complete|partial|failed)$/)
  detail = await read(casePath)
  const reviews = (detail.sourcing.reviews || []).map((r) => ({
    supplier: r.supplier_id,
    status: r.status,
    card: r.card?.status,
    unit_price_minor: r.card?.offer?.unit_price_minor,
    attempts: r.attempts?.length,
  }))
  expect(detail.sourcing.status, JSON.stringify(detail.sourcing.missing)).not.toBe('failed')
  await expect
    .poll(async () => (await read(casePath)).status, { timeout: 60000 })
    .toBe('OPTIONS_READY')
  detail = await read(casePath)
  const recommended = detail.proposal.candidates.find(
    (c) => c.id === detail.proposal.recommended_candidate_id,
  )
  await expect(panel.locator('[data-sourcing-review]').first()).toBeVisible()
  await step('sourcing-finished', {
    seconds: Math.round((Date.now() - started) / 1000),
    sourcing: detail.sourcing.status,
    reviews,
    recommended: recommended && {
      supplier: recommended.supplier_id,
      quantity: recommended.quantity,
      spend_minor: recommended.spend_minor,
    },
  })
  expect(recommended?.supplier_id, 'the solver should recommend a purchase').toBeTruthy()

  // The explanation follows the solve; it may still be writing.
  await expect
    .poll(async () => (await read(casePath)).expert_analysis?.status, {
      timeout: 180000,
      intervals: [3000],
    })
    .toMatch(/^(complete|partial|failed|unavailable|disabled)$/)
  detail = await read(casePath)
  const claims = (detail.expert_analysis?.subtasks || []).flatMap((t) => t.claims || [])
  await step('explanation', {
    status: detail.expert_analysis?.status,
    claims: claims.length,
    first_claim: claims[0]?.statement,
  })

  // 3. Adopt the recommended candidate, then approve it: the order waits for the supplier.
  await page
    .locator(`[data-recovery-candidate="${recommended.id}"]`)
    .getByRole('button', { name: '生成待确认方案' })
    .click()
  await expect.poll(async () => (await read(casePath)).plan_status).toBe('PENDING_APPROVAL')
  await page
    .getByRole('button', { name: `核对 ${recommended.quantity} 件采购`, exact: true })
    .click()
  await step('confirmation-dialog')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: new RegExp(`^确认采购 ${recommended.quantity} 件`) })
    .click()
  const card = page.locator('[data-assisted-order]')
  await expect(card).toBeVisible({ timeout: 60000 })
  const message = await card.locator('[data-order-message]').innerText()
  expect(message).toContain(`${recommended.quantity} 件`)
  const held = (await read('/api/v1/dashboard?store_id=' + store)).state.reserved_cash_minor
  expect(held).toBe(recommended.spend_minor)
  await step('order-message', { reserved_cash_minor: held, message })

  // 4. The owner pastes the supplier's reply. One that departs from the order confirms
  // nothing; one that agrees with it becomes the receipt.
  const sent = async () =>
    (await read('/api/v1/actions?store_id=' + store + '&limit=100')).items.find(
      (a) => a.channel === 'assisted',
    )
  const order = (await sent()).order_message
  await card.locator('[data-supplier-reply]').fill(`可以，但只有${order.quantity - 10}件`)
  await card.getByRole('button', { name: '登记回复', exact: true }).click()
  await expect.poll(async () => (await sent()).supplier_reply?.outcome, { timeout: 90000 }).toBe(
    'needs_attention',
  )
  let action = await sent()
  expect(action.status).toBe('EXECUTING')
  await expect(card).toBeVisible()
  await step('reply-differs', {
    read_by: action.supplier_reply.read_by,
    differences: action.supplier_reply.differences,
  })
  const price = (order.unit_price_minor / 100).toFixed(2)
  await card
    .locator('[data-supplier-reply]')
    .fill(reply || `好嘞老板，${order.quantity}件没问题，还是${price}元一件，周四给你送过去`)
  await card.getByRole('button', { name: '登记回复', exact: true }).click()
  const arrival = page.locator('[data-arrival-card]')
  await expect(arrival).toBeVisible({ timeout: 90000 })
  action = await sent()
  expect(action.status).toBe('SUCCEEDED')
  let stock = await stockOf(store, sku)
  expect(stock.in_transit).toBe(before.in_transit + recommended.quantity)
  await step('supplier-confirmed', {
    read_by: action.supplier_reply.read_by,
    outcome: action.supplier_reply.outcome,
    delivery_date: action.supplier_reply.delivery_date,
    quotes: action.supplier_reply.quotes,
    in_transit: stock.in_transit,
  })

  // 5. The goods arrive: the owner records them and they reach the shelf.
  await arrival.locator('[data-record-arrival]').click()
  await expect(arrival).toBeHidden({ timeout: 30000 })
  stock = await stockOf(store, sku)
  expect([stock.on_hand, stock.in_transit]).toEqual([
    before.on_hand + recommended.quantity,
    before.in_transit,
  ])
  const ledger = await read(
    '/api/v1/ledger-entries?store_id=' + store + '&effect_type=GOODS_RECEIVED',
  )
  expect(ledger.items[0].changes.on_hand_delta).toBe(recommended.quantity)
  await step('arrival-recorded', { on_hand: stock.on_hand, in_transit: stock.in_transit })

  // 6. The lineage of the prompt texts that ran.
  await page.goto(`${base}/?view=learning&store=${store}`)
  await expect(page.locator('body')).toContainText('提示词版本与自进化', { timeout: 30000 })
  await step('text-lineage')

  expect(errors).toEqual([])
  if (out)
    await writeFile(
      out + '/walkthrough.json',
      JSON.stringify({ status: 'passed', steps, page_errors: errors }, null, 2),
    )
  console.log(`PASS: ${steps.length} steps in a real browser against the running stack`)
} catch (error) {
  console.error('Browser page errors:', errors)
  console.error((await page.locator('body').innerText()).slice(0, 3000))
  if (out) {
    await page.screenshot({ path: out + '/failed.png', fullPage: true })
    await writeFile(
      out + '/walkthrough.json',
      JSON.stringify({ status: 'failed', steps, error: String(error) }, null, 2),
    )
  }
  throw error
} finally {
  await browser.close()
}
