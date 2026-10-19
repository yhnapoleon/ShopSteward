// Walks the emergency restock demo (workspace §18) in a real browser against a running stack:
// real HTTP, database and models, no request interception. It creates a synthetic SC01 store
// and drives the flow on the work page: brief, sourcing, one-click adopt and confirm, the order
// sent by hand with a partial and then a matching reply, the arrival and the result line.
//
// Before running:
// - DEMO_FRONTEND: the frontend's loopback URL (http://127.0.0.1:3000), signed in to a backend
//   identity with operator and approver rights (admin), so the confirmation opens at once.
// - The backend offers sourcing (session.sourcing) with its document-reading model configured,
//   and development tools (/dev/v1/scenarios) to create the SC01 store; the worker is running.
// - The explanation model is optional: without it the walk records that none was written.
// - DEMO_OUTPUT (optional) receives screenshots and walkthrough.json; DEMO_REPLY (optional) is
//   the confirming reply, otherwise written from the order; DEMO_HEADED=1 shows the browser.
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
      animations: 'disabled',
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
  // The owner works on the mission from its work item, as the today page opens it. Demo mode
  // keeps the sample supplier documents ready, as in the recording.
  const { item } = await write(`/api/v1/missions/${mission.id}/work-item`, {})
  await page.goto(`${base}/?view=work&store=${store}&item=${item.id}&demo=1`)
  await expect(page.locator('.space-workspace')).toBeVisible({ timeout: 30000 })
  const entry = page.locator('[data-recovery-entry]')
  await expect(entry).toBeVisible({ timeout: 30000 })
  await step('work-item', { store, on_hand: before.on_hand, in_transit: before.in_transit })

  // 1. The brief: everything is filled in from the store's facts; the owner only confirms.
  const flow = page.locator('[data-recovery-flow]')
  const next = flow.locator('[data-recovery-next]')
  await entry.click()
  await expect(flow).toHaveAttribute('data-stage', 'brief')
  await expect(flow.locator('[data-fact="documents"] b')).toHaveText(/^[1-9]\d* 家$/, {
    timeout: 30000,
  })
  // The first settlement follows the business clock; it shows only while editing.
  await flow.getByRole('button', { name: '修改', exact: true }).click()
  const firstSettlement = await flow.locator('[data-fact="settlement"] b').innerText()
  await flow.getByRole('button', { name: '改好了', exact: true }).click()
  await step('brief', {
    budget: await flow.locator('[data-fact="budget"] b').innerText(),
    demand: await flow.locator('[data-fact="demand"] b').innerText(),
    first_settlement: firstSettlement,
  })
  // With no gap over the seven days, closing is the main action and comparing anyway a link.
  const start = flow.locator('[data-recovery-start]')
  if (await start.isVisible()) await start.click()
  else await next.click()
  let detail
  await expect
    .poll(
      async () => {
        const list = await read('/api/v1/operations-cases?store_id=' + store)
        detail = list.items[0] && (await read('/api/v1/operations-cases/' + list.items[0].id))
        return detail?.sourcing?.status
      },
      { timeout: 60000 },
    )
    .toBeTruthy()
  const casePath = '/api/v1/operations-cases/' + detail.id
  await step('case-sourcing', { case_id: detail.id, revision: detail.current_revision })

  // 2. Sourcing: one reviewer per supplier reads the sample documents; the flow shows each one.
  const started = Date.now()
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
  await expect(flow.locator(`[data-recovery-option="${recommended.supplier_id}"]`)).toBeVisible({
    timeout: 30000,
  })
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

  // The explanation follows the solve; it may still be writing. It stays folded on the page.
  // Without an explanation model nothing is written ("none"), and the walk does not wait.
  await expect
    .poll(async () => (await read(casePath)).expert_analysis?.status ?? 'none', {
      timeout: 180000,
      intervals: [3000],
    })
    .toMatch(/^(complete|partial|failed|unavailable|disabled|none)$/)
  detail = await read(casePath)
  const claims = (detail.expert_analysis?.subtasks || []).flatMap((t) => t.claims || [])
  await step('explanation', {
    status: detail.expert_analysis?.status,
    claims: claims.length,
    first_claim: claims[0]?.statement,
  })

  // 3. One click adopts the recommendation and opens the confirmation; confirming sends the
  // order to the owner (the supplier was read from documents, so the owner sends it).
  await expect(next).toHaveText(new RegExp(`补 ${recommended.quantity} 件$`))
  await next.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('核对这笔采购', { timeout: 30000 })
  await step('confirmation-dialog')
  await dialog
    .getByRole('button', { name: new RegExp(`^确认采购 ${recommended.quantity} 件`) })
    .click()
  await expect(flow).toHaveAttribute('data-stage', 'order', { timeout: 60000 })
  const message = await flow.locator('[data-order-message]').innerText()
  expect(message).toContain(`${recommended.quantity} 件`)
  const held = (await read('/api/v1/dashboard?store_id=' + store)).state.reserved_cash_minor
  expect(held).toBe(recommended.spend_minor)
  await step('order-message', { reserved_cash_minor: held, message })

  // 4. The owner pastes the supplier's reply. One that offers only part confirms nothing and
  // offers to switch suppliers; one that agrees with the order becomes the receipt.
  const sent = async () =>
    (await read('/api/v1/actions?store_id=' + store + '&limit=100')).items.find(
      (a) => a.channel === 'assisted',
    )
  const order = (await sent()).order_message
  // Half the order (an order of one unit cannot be filled in part, so that step is skipped).
  const part = Math.floor(order.quantity / 2)
  const price = (order.unit_price_minor / 100).toFixed(2)
  const confirming =
    reply || `好嘞老板，${order.quantity}件没问题，还是${price}元一件，明天给你送过去`
  if (part > 0) {
    await flow.locator('[data-supplier-reply]').fill(`可以，但只有${part}件`)
    await next.click()
    await expect
      .poll(async () => (await sent()).supplier_reply?.outcome, { timeout: 90000 })
      .toBe('partial')
    const partial = await sent()
    expect(partial.status).toBe('EXECUTING')
    // Taking the smaller quantity leads; withdrawing the whole order stays a second way.
    await expect(flow.locator('[data-accept-partial]')).toBeVisible({ timeout: 30000 })
    await expect(flow.locator('[data-recovery-switch]')).toBeVisible()
    await step('reply-partial', {
      read_by: partial.supplier_reply.read_by,
      quantity: partial.supplier_reply.quantity,
    })
    // Beside a partial offer the reply box waits behind "登记新回复".
    await flow.locator('[data-recovery-new-reply]').click()
    await flow.locator('[data-supplier-reply]').fill(confirming)
    await flow.locator('[data-recovery-submit-reply]').click()
  } else {
    await flow.locator('[data-supplier-reply]').fill(confirming)
    await next.click()
  }
  await expect(flow).toHaveAttribute('data-stage', 'receive', { timeout: 90000 })
  let action = await sent()
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

  // 5. The goods arrive: the owner records them, they reach the shelf, the card shows the result.
  await flow.locator('[data-record-arrival]').click()
  await expect(flow.locator('[data-recovery-summary]')).toBeVisible({ timeout: 30000 })
  stock = await stockOf(store, sku)
  expect([stock.on_hand, stock.in_transit]).toEqual([
    before.on_hand + recommended.quantity,
    before.in_transit,
  ])
  const ledger = await read(
    '/api/v1/ledger-entries?store_id=' + store + '&effect_type=GOODS_RECEIVED',
  )
  expect(ledger.items[0].changes.on_hand_delta).toBe(recommended.quantity)
  await step('arrival-recorded', {
    on_hand: stock.on_hand,
    in_transit: stock.in_transit,
    summary: await flow.locator('[data-recovery-summary]').innerText(),
  })

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
    await page.screenshot({ path: out + '/failed.png', fullPage: true, animations: 'disabled' })
    await writeFile(
      out + '/walkthrough.json',
      JSON.stringify({ status: 'failed', steps, error: String(error) }, null, 2),
    )
  }
  throw error
} finally {
  await browser.close()
}
