import { readFileSync } from 'node:fs'
import { expect, type Page } from '@playwright/test'

// A stateful stand-in for the business API behind the emergency restock flow (workspace §18):
// recovery Cases, sourcing over three sample suppliers, plans and their approval, an order the
// owner sends by hand, its reply and its arrival. Quantities follow the recovery solver's own
// rules (backend planning/recovery/solver.py): daily settlement, minimum order, whole cases,
// budget and cash floor. Nothing reaches a real backend.

const DAY = 86_400_000
const nowIso = () => new Date().toISOString()
export const SUPPLIERS = [
  { id: 'A', name: '安和商贸', price: 1020, lead: 2 },
  { id: 'B', name: '百川批发', price: 950, lead: 1 },
  { id: 'C', name: '诚达供应链', price: 860, lead: 0, noOffer: 'STORE_NOT_SERVED' },
] as const

export type Options = {
  roles?: string[]
  recoveryCases?: boolean
  workIntake?: boolean
  /** Supplier documents already on file when the page opens. */
  documents?: boolean
  /** Demo mode (the brief loads the sample documents by itself). */
  demo?: boolean
  /** Where the owner starts: the mission's work page or the today page. */
  entry?: 'work' | 'today'
  /** Changes the fixture or the mock before the page loads. */
  prepare?: (f: any, m: Mock) => void
}

export type Mock = ReturnType<typeof createMock>

export function createMock(options: Options = {}) {
  const f = JSON.parse(
    readFileSync(new URL('../fixtures/overview-pending.json', import.meta.url), 'utf8'),
  )
  const mission = f.missions.items[0]
  const store = mission.store_id
  const sku = mission.sku_id
  const clock = () => Date.parse(f.dashboard.state.simulation_time)
  const stock = () => f.dashboard.state.stocks[0]
  const now = Date.now()
  f.plan.expires_at = '2099-01-01T00:00:00Z'
  const work = {
    id: 'work-one',
    store_id: store,
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
    business: null as any,
  }
  const m = {
    f,
    mission,
    work,
    store,
    sku,
    writes: [] as { path: string; key: string | undefined; body: any }[],
    item: null as any,
    documents: [] as any[],
    plans: {} as Record<string, any>,
    /** Reviews still to arrive, one per read of the Case while sourcing runs. */
    reviewing: [] as string[],
    /** Whether a sourcing run also writes the (folded) model explanation. */
    explanation: true,
    /** Analyses still to fail with DATA_STALE, as when the business data is not synced yet. */
    failAnalyze: 0,
    /** Case writes that take effect but whose answer is lost (a 503 afterwards), once per entry. */
    loseReply: [] as string[],
    /** Answers already given, by idempotency key: a repeated key gets the first answer back. */
    replies: {} as Record<string, any>,
    session: {
      authenticated: true,
      principal_id: 'test-owner',
      roles: options.roles || ['admin'],
      agentEnabled: false,
      devTools: false,
      workIntake: options.workIntake ?? true,
      planRevision: true,
      recoveryCases: options.recoveryCases ?? true,
      sourcing: true,
    },
  }
  const sampleDocuments = () =>
    SUPPLIERS.map((s) => ({
      supplier_id: s.id,
      name: s.name,
      connected: false,
      documents: [
        { doc_id: `${s.id}-quote`, kind: 'quote', text: `${s.name} 商品报价单` },
        { doc_id: `${s.id}-terms`, kind: 'terms', text: `${s.name} 供货合作条款` },
      ],
    }))
  if (options.documents) m.documents = sampleDocuments()
  // Sourcing reads the documents on file, so it reports the names written there.
  const nameOf = (s: (typeof SUPPLIERS)[number]) =>
    m.documents.find((d: any) => d.supplier_id === s.id)?.name ?? s.name

  // ---- the solver's day-by-day settlement ----
  const offerFor = (s: (typeof SUPPLIERS)[number]) => ({
    supplier_id: s.id,
    sku_id: sku,
    unit_price_minor: s.price,
    minimum_order_quantity: 20,
    pack_size: 10,
    offer_version: `BJ-${s.id}-01`,
    currency: 'CNY',
    lead_time_seconds: s.lead * 86400,
    valid_from: new Date(now - 10 * DAY).toISOString(),
    valid_until: new Date(now + 30 * DAY).toISOString(),
  })
  function trajectory(c: any, quantity: number, arrival: number | null) {
    let level = stock().on_hand
    let pending = f.inbounds.items
      .filter((i: any) => i.remaining_quantity > 0)
      .map((i: any) => ({ qty: i.remaining_quantity, at: i.expected_arrival_at }))
    let proposed = quantity
    return c.daily_demand.map((d: any) => {
      const end = Date.parse(d.settlement_at)
      const due = pending.filter(
        (a: any) => a.at && Date.parse(a.at) >= clock() && Date.parse(a.at) <= end,
      )
      pending = pending.filter((a: any) => !due.includes(a))
      const existing = due.reduce((n: number, a: any) => n + a.qty, 0)
      const received = arrival != null && arrival <= end ? proposed : 0
      proposed -= received
      const available = level + existing + received
      const served = Math.min(available, d.demand_qty)
      level = available - served
      return {
        ...d,
        existing_arrivals: existing,
        proposed_arrivals: received,
        served_qty: served,
        lost_qty: d.demand_qty - served,
        end_stock: level,
      }
    })
  }
  function solve(c: any) {
    const offers = f.catalog.offers.filter(
      (o: any) => o.sku_id === sku && (!c.supplier_ids || c.supplier_ids.includes(o.supplier_id)),
    )
    const cash = f.dashboard.state.available_cash_minor
    const floor = mission.policy.cash_floor_minor
    const candidates: any[] = []
    const add = (offer: any, quantity: number) => {
      const spend = offer ? quantity * offer.unit_price_minor : 0
      const reasons: string[] = []
      const arrival = offer ? clock() + offer.lead_time_seconds * 1000 : null
      if (offer) {
        if (
          !(
            Date.parse(offer.valid_from) <= Date.now() && Date.now() < Date.parse(offer.valid_until)
          )
        )
          reasons.push('OFFER_EXPIRED')
        if (quantity < offer.minimum_order_quantity) reasons.push('MINIMUM_ORDER_QUANTITY')
        if (quantity % offer.pack_size) reasons.push('PACK_SIZE_MISMATCH')
        if (arrival! > Date.parse(c.daily_demand.at(-1).settlement_at))
          reasons.push('ARRIVAL_WINDOW_MISSED')
      }
      if (spend > c.budget_minor) reasons.push('BUDGET_EXCEEDED')
      if (cash - spend < floor) reasons.push('CASH_FLOOR_VIOLATION')
      const daily = trajectory(c, quantity, arrival)
      const lost = daily.reduce((n: number, d: any) => n + d.lost_qty, 0)
      candidates.push({
        id: offer ? `${offer.supplier_id}_${quantity}` : 'wait',
        supplier_id: offer ? offer.supplier_id : null,
        quantity,
        spend_minor: spend,
        cash_after_minor: cash - spend,
        lost_qty: lost,
        shortage_qty: lost,
        end_stock: daily.at(-1).end_stock,
        feasible: !reasons.length,
        executable: !!quantity && !reasons.length,
        rejection_reasons: reasons,
        daily,
      })
    }
    add(null, 0)
    for (const offer of [...offers].sort((a, b) => a.supplier_id.localeCompare(b.supplier_id))) {
      const minimum = Math.ceil(offer.minimum_order_quantity / offer.pack_size) * offer.pack_size
      const room = Math.max(0, Math.min(c.budget_minor, cash - floor))
      const maximum = Math.floor(room / offer.unit_price_minor)
      if (maximum < minimum) add(offer, minimum)
      for (let q = minimum; q <= maximum; q += offer.pack_size) add(offer, q)
    }
    const rank = (x: any) => [
      x.lost_qty,
      x.spend_minor,
      x.end_stock,
      x.supplier_id || '',
      x.quantity,
    ]
    const best = candidates
      .filter((x) => x.feasible)
      .sort((a, b) => {
        const p = rank(a),
          q = rank(b)
        for (let i = 0; i < p.length; i++) if (p[i] !== q[i]) return p[i] < q[i] ? -1 : 1
        return 0
      })[0]
    return {
      id: `proposal-${c.id}-${c.current_revision}`,
      case_id: c.id,
      revision: c.current_revision,
      snapshot_hash: 'snapshot',
      candidate_set_hash: 'candidates',
      proposal_hash: `hash-${c.current_revision}`,
      created_at: new Date().toISOString(),
      expires_at: '2099-01-01T00:00:00Z',
      recommended_candidate_id: best?.id ?? null,
      horizon_tail: [],
      candidates,
    }
  }
  const evidence = () =>
    f.inbounds.items
      .filter((i: any) => i.remaining_quantity > 0)
      .map((i: any) => ({
        id: i.action_id,
        kind: 'inbound_order',
        version: '3',
        status: 'verified_source',
        summary: `未到货 ${i.remaining_quantity} 件；原订单保留`,
      }))
  function analyze() {
    const c = m.item
    c.proposal = solve(c)
    c.status = 'OPTIONS_READY'
    c.stale = false
    c.evidence = evidence()
    c.missing_inputs = []
  }
  function revise(changes: any) {
    const c = m.item
    if (c.plan_status === 'PENDING_APPROVAL') {
      c.plan_status = 'SUPERSEDED'
      if (f.plan.id === c.plan_id) f.plan.status = 'SUPERSEDED'
    }
    Object.assign(c, changes)
    c.current_revision++
    c.status = 'OPEN'
    c.proposal = null
    c.expert_analysis = null
  }
  // One reviewer finishes per read of the Case, then the readable offers are registered.
  function advanceSourcing() {
    const c = m.item
    if (c?.sourcing?.status !== 'running') return
    const next = m.reviewing.shift()
    if (next) {
      const s = SUPPLIERS.find((x) => x.id === next)!
      const offer = 'noOffer' in s ? null : offerFor(s)
      c.sourcing.reviews.push({
        supplier_id: s.id,
        name: nameOf(s),
        status: 'accepted',
        card: {
          supplier_id: s.id,
          status: offer ? 'offer' : 'no_offer',
          reason: offer ? null : (s as any).noOffer,
          offer: offer && {
            unit_price_minor: offer.unit_price_minor,
            minimum_order_quantity: 20,
            pack_size: 10,
            lead_time_days: s.lead,
            valid_from: offer.valid_from.slice(0, 10),
            valid_until: offer.valid_until.slice(0, 10),
            offer_version: offer.offer_version,
          },
          history: { deliveries: 5, late: s.id === 'A' ? 1 : 0 },
          citations: [
            {
              field: offer ? 'unit_price_minor' : 'status',
              doc_id: `${s.id}-quote`,
              quote: offer ? `单价 ${(s.price / 100).toFixed(2)} 元` : '配送范围：萧山区、余杭区',
            },
          ],
        },
        attempts: [
          { attempt: 1, model: 'test', opened: [`${s.id}-quote`], problems: [], reasons: [] },
        ],
      })
      return
    }
    const registered = SUPPLIERS.filter((s) => !('noOffer' in s))
      .sort((a, b) => a.price - b.price)
      .map((s) => s.id)
    // Reading the documents again registers the current quote in place of an older one.
    for (const id of registered) {
      const offer = offerFor(SUPPLIERS.find((s) => s.id === id)!)
      const at = f.catalog.offers.findIndex((o: any) => o.supplier_id === id)
      if (at >= 0) f.catalog.offers[at] = offer
      else f.catalog.offers.push(offer)
    }
    c.sourcing = { ...c.sourcing, status: 'complete', registered, left_out: [], unreviewed: [] }
    revise({ supplier_ids: registered })
    analyze()
    c.sourcing.revision = c.current_revision
    if (m.explanation)
      c.expert_analysis = {
        status: 'partial',
        strategy: 'fixed',
        subtasks: [
          {
            subtask_id: 'fixed',
            role: 'fixed',
            status: 'partial',
            claims: [
              {
                statement: 'B offers the lowest unit price among the readable quotes.',
                support: [],
              },
              { statement: 'C does not deliver to the store district.', support: [] },
            ],
          },
        ],
      }
  }
  function caseOf(body: any) {
    return {
      id: 'case-one',
      mission_id: mission.id,
      store_id: store,
      sku_id: sku,
      status: 'OPEN',
      current_revision: 1,
      objective: body.objective,
      budget_minor: body.budget_minor,
      max_purchase_qty: body.max_purchase_qty ?? null,
      daily_demand: body.daily_demand ?? null,
      supplier_ids: body.supplier_ids ?? null,
      proposal: null,
      plan_id: null,
      plan_status: null,
      plan_revision: null,
      action_id: null,
      execution_status: null,
      missing_inputs: [],
      evidence: [],
      current_mission_version: mission.mission_version,
      current_state_version: f.dashboard.state.state_version,
      current_plan_id: mission.current_plan_id,
      stale: false,
      expert_analysis: null,
      sourcing: null,
      followup_enabled: false,
      created_at: nowIso(),
      updated_at: nowIso(),
    }
  }
  function materialize(candidateId: string) {
    const c = m.item
    const chosen = c.proposal.candidates.find((x: any) => x.id === candidateId)
    const offer = f.catalog.offers.find((o: any) => o.supplier_id === chosen.supplier_id)
    const id = `recovery-plan-${c.current_revision}`
    const plan = {
      ...f.plan,
      id,
      plan_kind: 'recovery_v1',
      status: 'PENDING_APPROVAL',
      plan_version: f.plan.plan_version + 1,
      selected_candidate_id: chosen.id,
      recommended_candidate_id: c.proposal.recommended_candidate_id,
      recovery_intent: {
        case_id: c.id,
        revision: c.current_revision,
        proposal_id: c.proposal.id,
        selected_candidate_id: chosen.id,
        adopted_by: 'test-owner',
        supplier_override: chosen.supplier_id,
      },
      candidates: c.proposal.candidates.map((x: any) => ({ ...x, shortage_qty: x.lost_qty })),
      proposed_purchase: {
        store_id: store,
        sku_id: sku,
        supplier_id: chosen.supplier_id,
        quantity: chosen.quantity,
        unit_price_minor: offer.unit_price_minor,
        total_minor: chosen.spend_minor,
        currency: 'CNY',
        expected_arrival_at: new Date(clock() + offer.lead_time_seconds * 1000).toISOString(),
      },
      input_snapshot: { ...f.plan.input_snapshot, offer },
      expires_at: '2099-01-01T00:00:00Z',
    }
    m.plans[id] = plan
    f.plan = plan
    mission.current_plan_id = id
    c.plan_id = id
    c.plan_status = 'PENDING_APPROVAL'
    c.plan_revision = c.current_revision
  }
  function approve() {
    const plan = f.plan
    const p = plan.proposed_purchase
    const assisted = SUPPLIERS.some((s) => s.id === p.supplier_id)
    const reference = 'PO-1A2B3C4D'
    const action = {
      id: 'action-one',
      mission_id: mission.id,
      plan_id: plan.id,
      approval_id: 'approval-one',
      status: assisted ? 'EXECUTING' : 'SUCCEEDED',
      channel: assisted ? 'assisted' : 'simulator',
      quantity: p.quantity,
      amount_minor: p.total_minor,
      currency: 'CNY',
      external_order_id: null,
      receipt: null,
      last_error: null,
      order_message: assisted
        ? {
            reference,
            supplier_id: p.supplier_id,
            sku_id: sku,
            product_name: f.catalog.products[0].name,
            quantity: p.quantity,
            unit_price_minor: p.unit_price_minor,
            total_minor: p.total_minor,
            currency: 'CNY',
            requested_delivery_date: p.expected_arrival_at.slice(0, 10),
            text: {
              zh: `【订货单 ${reference}】\n数量：${p.quantity} 件\n单价：${(p.unit_price_minor / 100).toFixed(2)} 元/件`,
              en: `[Purchase order ${reference}]\nQuantity: ${p.quantity} units`,
            },
            generated_at: nowIso(),
          }
        : null,
      supplier_reply: null,
      created_at: nowIso(),
      updated_at: nowIso(),
      purchase_snapshot: { ...p },
    }
    plan.status = 'APPROVED'
    f.actions.items = [action, ...f.actions.items]
    f.dashboard.state.reserved_cash_minor += p.total_minor
    f.dashboard.state.available_cash_minor -= p.total_minor
    if (m.item?.plan_id === plan.id) {
      m.item.plan_status = 'APPROVED'
      m.item.action_id = action.id
      m.item.execution_status = action.status
    }
    if (assisted) mission.current_action_id = action.id
    else accept(action)
  }
  const release = (action: any) => {
    f.dashboard.state.reserved_cash_minor -= action.amount_minor
    f.dashboard.state.available_cash_minor += action.amount_minor
    mission.current_action_id = null
  }
  function accept(action: any) {
    action.status = 'SUCCEEDED'
    // The reserved cash becomes the purchase: available cash was already reduced at approval.
    f.dashboard.state.reserved_cash_minor -= action.amount_minor
    f.dashboard.state.cash_minor -= action.amount_minor
    stock().in_transit += action.quantity
    f.inbounds.items.push({
      action_id: action.id,
      mission_id: mission.id,
      sku_id: sku,
      external_order_id: 'SUP-1',
      ordered_quantity: action.quantity,
      received_quantity: 0,
      remaining_quantity: action.quantity,
      expected_arrival_at: action.purchase_snapshot.expected_arrival_at,
      arrival_status: 'NOT_RECEIVED',
      is_overdue: false,
    })
    mission.current_action_id = null
    if (m.item?.action_id === action.id) m.item.execution_status = 'ACCEPTED'
  }
  function reply(action: any, text: string) {
    const replied = Number(/(\d+)\s*件/.exec(text)?.[1] ?? action.quantity)
    const declined = /抱歉|没货|不能|无法/.test(text)
    const outcome = declined
      ? 'declined'
      : replied !== action.quantity
        ? 'needs_attention'
        : 'confirmed'
    action.supplier_reply = {
      text,
      read_by: 'rules',
      outcome,
      decision: declined ? 'rejected' : 'accepted',
      quantity: replied,
      unit_price_minor: null,
      total_minor: null,
      delivery_date: null,
      supplier_order_ref: null,
      quotes: { quantity: `${replied}件` },
      differences:
        outcome === 'needs_attention'
          ? [{ field: 'quantity', ordered: action.quantity, replied }]
          : [],
      recorded_at: nowIso(),
      recorded_by: 'test-owner',
    }
    if (outcome === 'declined') {
      action.status = 'FAILED'
      release(action)
      if (m.item?.action_id === action.id) m.item.execution_status = 'FAILED'
    } else if (outcome === 'confirmed') accept(action)
    return action
  }
  function arrive(action: any, quantity: number) {
    const inbound = f.inbounds.items.find((i: any) => i.action_id === action.id)
    inbound.received_quantity += quantity
    inbound.remaining_quantity -= quantity
    inbound.arrival_status = inbound.remaining_quantity ? 'PARTIALLY_RECEIVED' : 'RECEIVED'
    stock().on_hand += quantity
    stock().in_transit -= quantity
    if (m.item?.action_id === action.id)
      m.item.execution_status = inbound.remaining_quantity ? 'PARTIALLY_RECEIVED' : 'RECEIVED'
    return action
  }
  return Object.assign(m, {
    clock,
    stock,
    sampleDocuments,
    nameOf,
    offerFor,
    solve,
    analyze,
    revise,
    advanceSourcing,
    caseOf,
    materialize,
    approve,
    accept,
    reply,
    arrive,
    release,
  })
}

/** Routes every request of the page to the mock; returns it for assertions and changes. */
export async function setupRecovery(page: Page, options: Options = {}) {
  const m = createMock(options)
  const { f, mission } = m
  options.prepare?.(f, m)
  await page.route('**/api/**', async (route) => {
    const r = route.request(),
      u = new URL(r.url()),
      path = u.pathname.replace('/api/backend/api/v1/', '')
    if (u.pathname === '/api/session') return route.fulfill({ json: m.session })
    if (u.pathname === '/api/health') return route.fulfill({ json: { backend: 'ok' } })
    const json = (value: unknown, status = 200) => route.fulfill({ status, json: value })
    const fail = (status: number, code: string) =>
      route.fulfill({ status, json: { error: { code, message: code } } })
    if (r.method() !== 'GET') {
      const body = r.postDataJSON() || {}
      m.writes.push({ path, key: r.headers()['idempotency-key'], body })
      if (path === `missions/${mission.id}/work-item`) return json({ item: m.work, messages: [] })
      if (path.endsWith('/supplier-documents/sample')) {
        m.documents = m.sampleDocuments()
        return json({ store_id: m.store, suppliers: m.documents })
      }
      if (path === 'operations-cases') {
        m.item = m.caseOf(body)
        return json(m.item, 201)
      }
      const action = f.actions.items.find((a: any) => path.startsWith(`actions/${a.id}/`))
      if (action && path.endsWith('/supplier-reply')) return json(m.reply(action, body.text))
      if (action && path.endsWith('/withdrawal')) {
        action.status = 'CANCELLED'
        m.release(action)
        if (m.item?.action_id === action.id) m.item.execution_status = 'CANCELLED'
        return json(action)
      }
      if (action && path.endsWith('/arrival')) return json(m.arrive(action, body.quantity))
      if (/^plans\/[^/]+\/decision$/.test(path)) {
        if (body.decision === 'approve') m.approve()
        else f.plan.status = 'REJECTED'
        return json({ plan_id: f.plan.id, status: 'APPROVED' })
      }
      const c = m.item
      if (!c || !path.startsWith(`operations-cases/${c.id}/`))
        return fail(409, 'BLOCKED_TEST_WRITE')
      const key = r.headers()['idempotency-key']
      if (key && m.replies[key]) return json(m.replies[key])
      if (body.expected_revision !== undefined && body.expected_revision !== c.current_revision)
        return fail(409, 'CASE_REVISION_CONFLICT')
      const op = path.split('/').at(-1)
      if (op === 'analyze' && m.failAnalyze > 0) {
        m.failAnalyze--
        return fail(409, 'DATA_STALE')
      }
      if (op === 'analyze') m.analyze()
      else if (op === 'revise') {
        const { expected_revision: _, ...changes } = body
        m.revise(changes)
      } else if (op === 'source') {
        c.sourcing = {
          status: 'running',
          run_id: 'run-one',
          revision: c.current_revision,
          request: {
            sku_id: m.sku,
            district: body.district,
            as_of: '2026-09-07',
            shortfall_qty: c.proposal?.candidates.find((x: any) => x.id === 'wait')?.lost_qty ?? 0,
            short_from: '2026-09-10',
          },
          suppliers: SUPPLIERS.map((s) => ({
            supplier_id: s.id,
            name: m.nameOf(s),
            documents: [{ doc_id: `${s.id}-quote`, kind: 'quote' }],
          })),
          reviews: [],
        }
        m.reviewing = SUPPLIERS.map((s) => s.id)
      } else if (op === 'materialize') m.materialize(body.candidate_id)
      else if (op === 'control') {
        if (body.operation === 'cancel') c.status = 'CANCELLED'
        if (body.operation === 'adopt_waiting') {
          c.status = 'MONITORING'
          if (c.plan_status === 'PENDING_APPROVAL') c.plan_status = 'SUPERSEDED'
        }
        if (body.operation === 'refresh') m.revise({})
      } else return fail(409, 'BLOCKED_TEST_WRITE')
      c.updated_at = nowIso()
      if (key) m.replies[key] = structuredClone(c)
      const lost = m.loseReply.indexOf(op!)
      if (lost >= 0) {
        m.loseReply.splice(lost, 1)
        return fail(503, 'SERVICE_UNAVAILABLE')
      }
      return json(c)
    }
    if (path === 'operations-cases')
      return json({ items: m.item ? [m.item] : [], next_cursor: null })
    if (m.item && path === `operations-cases/${m.item.id}`) {
      m.advanceSourcing()
      return json(m.item)
    }
    if (path === `stores/${m.store}/supplier-documents`)
      return json({ store_id: m.store, suppliers: m.documents })
    if (path === `stores/${m.store}/forecast`) return fail(404, 'FORECAST_NOT_FOUND')
    if (path === 'work-items')
      return json({ items: [m.work], next_cursor: null, processor_available: false })
    if (path === 'work-items/work-one') return json({ item: m.work, messages: [] })
    if (path === 'stores')
      return json({
        items: [{ store_id: m.store, currency: 'CNY', source_type: 'simulation' }],
        active_store: { store_id: m.store },
        next_cursor: null,
      })
    if (path === `missions/${mission.id}`) return json(mission)
    if (path.endsWith('/timeline')) return json(f.timeline)
    if (path.endsWith('/plans')) return json({ items: [f.plan], next_cursor: null })
    if (path.startsWith('plans/')) return json(m.plans[path.slice(6)] || f.plan)
    if (f[path]) return json(f[path])
    return fail(404, 'MISSING_TEST_READ')
  })
  if (options.demo) await page.addInitScript(() => localStorage.setItem('ss.demo.v1', '1'))
  if (options.entry === 'today') {
    await page.goto('/?store=' + m.store)
    await expect(page.locator('#decision-zone')).toBeVisible()
  } else {
    await page.goto(`/?view=work&item=${m.work.id}&store=${m.store}`)
    await expect(page.locator('.space-workspace.task-workspace')).toBeVisible()
  }
  return m
}

/** The local month/day label the page shows for a settlement time. */
export const dayLabel = (at: number | string) =>
  new Date(at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
