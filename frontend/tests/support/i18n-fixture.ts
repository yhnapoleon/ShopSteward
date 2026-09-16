import { type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
const fixture = JSON.parse(
  readFileSync(new URL('../fixtures/overview.json', import.meta.url), 'utf8'),
)
const pendingFixture = JSON.parse(
  readFileSync(new URL('../fixtures/overview-pending.json', import.meta.url), 'utf8'),
)

// Entire browser transport is controlled. No test in this file creates a store,
// changes the simulator, sends a model request, or forwards a purchase.
type Controls = {
  active: string
  failures: Set<string>
  delaySales: number
  detailDelay: number
  salesCount: number
  mixed: boolean
  partial: boolean
  noMission: boolean
  pendingDecision: boolean
  staleLedger: boolean
  calls: string[]
  writes: string[]
}
export async function setup(page: Page) {
  const control: Controls = {
    active: 'overview-fixture-a',
    failures: new Set(),
    delaySales: 0,
    detailDelay: 0,
    salesCount: 1,
    mixed: false,
    partial: false,
    noMission: false,
    pendingDecision: false,
    staleLedger: false,
    calls: [],
    writes: [],
  }
  await page.route('**/api/**', async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname.replace('/api/backend/api/v1/', '')
    control.calls.push(path)
    if (req.method() !== 'GET') {
      control.writes.push(path)
      return route.fulfill({
        status: 409,
        json: {
          error: { code: 'TEST_WRITE_BLOCKED', message: 'No writes are forwarded by this test.' },
        },
      })
    }
    if (url.pathname === '/api/session')
      return route.fulfill({
        json: {
          authenticated: true,
          principal_id: 'test-owner',
          roles: ['admin'],
          store_scope: 'ALL',
          agentEnabled: false,
          devTools: true,
          planRevision: true,
        },
      })
    const id = url.searchParams.get('store_id') || control.active
    const b = id.endsWith('-b')
    const f: any = JSON.parse(
      JSON.stringify(control.pendingDecision ? pendingFixture : fixture).replaceAll(
        'overview-fixture-a',
        id,
      ),
    )
    if (b) {
      Object.assign(f.dashboard.state, {
        cash_minor: 123400,
        available_cash_minor: 123400,
        receivables_minor: 0,
        state_version: 1,
      })
      Object.assign(f.dashboard.state.stocks[0], { on_hand: 37, in_transit: 0 })
      f.inbounds.items = []
      f.actions.items = []
      f.missions.items = []
      f.plan = null
      const initial = f['ledger-entries'].items.find((x: any) => x.effect_type === 'INIT')
      initial.opening_state = structuredClone(f.dashboard.state)
      initial.state_version = 1
      f['ledger-entries'].items = [initial]
    }
    // S5 for the visual fixture, using only supported fields and no backend writes.
    if (!b && !control.pendingDecision) {
      f.dashboard.state.simulation_time = f['ledger-entries'].items.find(
        (x: any) => x.effect_type === 'DEMAND_REVISED',
      ).simulation_time
      f['ledger-entries'].items = f['ledger-entries'].items.filter(
        (x: any) => !(x.effect_type === 'GOODS_RECEIVED' && x.changes?.on_hand_delta === 20),
      )
      Object.assign(f.dashboard.state.stocks[0], { on_hand: 50, in_transit: 20 })
      const second = f.inbounds.items.find((x: any) => x.ordered_quantity === 20)
      Object.assign(second, {
        received_quantity: control.partial ? 5 : 0,
        remaining_quantity: control.partial ? 15 : 20,
        arrival_status: control.partial ? 'PARTIALLY_RECEIVED' : 'NOT_RECEIVED',
        expected_arrival_at: control.partial ? null : second.expected_arrival_at,
        is_overdue: control.partial ? null : false,
      })
    }
    if (control.noMission) {
      f.missions.items = []
      f.plan = null
    }
    const ctx = structuredClone(f.sales.context)
    Object.assign(ctx, {
      store_id: id,
      state_version: f.dashboard.state.state_version,
      simulation_time: f.dashboard.state.simulation_time,
    })
    for (const resource of ['sales', 'inbounds', 'actions', 'ledger-entries'])
      f[resource].context = structuredClone(ctx)
    if (control.staleLedger) f['ledger-entries'].context.freshness.status = 'STALE'
    if (path === 'stores') {
      const store = (store_id: string) => ({
        store_id,
        currency: 'CNY',
        source_type: 'simulation',
        simulation_time: f.dashboard.state.simulation_time,
      })
      return route.fulfill({
        json: {
          items: [store('overview-fixture-a'), store('overview-fixture-b')],
          next_cursor: null,
          active_store: store(control.active),
        },
      })
    }
    if (control.failures.has(path))
      return route.fulfill({
        status: 503,
        json: { error: { code: 'READ_FAILED', message: '受控读取失败' } },
      })
    if (path === 'sales/summary' || path === 'sales') {
      const from = url.searchParams.get('from') || '2026-09-01T00:00:00Z',
        to = url.searchParams.get('to') || '2026-09-10T00:00:00Z'
      const source = f.sales.items[0]
      const records = b
        ? []
        : Array.from({ length: control.salesCount }, (_, i) => ({
            ...source,
            event_id: `sale-${i}`,
            sequence: i + 1,
            quantity: control.salesCount === 1 ? 10 : 1,
            sales_amount_minor: control.salesCount === 1 ? 20000 : 2000,
          }))
      const filtered = records.filter(
        (x) =>
          Date.parse(x.simulation_time) >= Date.parse(from) &&
          Date.parse(x.simulation_time) < Date.parse(to),
      )
      if (control.mixed) ctx.state_version += 1
      if (path === 'sales/summary') {
        const buckets = []
        for (let t = Date.parse(from); t < Date.parse(to); t += 86400000) {
          const matches = filtered.filter(
            (x) =>
              Date.parse(x.simulation_time) >= t && Date.parse(x.simulation_time) < t + 86400000,
          )
          buckets.push({
            from: new Date(t).toISOString(),
            to: new Date(Math.min(t + 86400000, Date.parse(to))).toISOString(),
            record_count: matches.length,
            recorded_quantity: matches.reduce((n, x) => n + x.quantity, 0),
            recorded_sales_amount_minor: matches.reduce((n, x) => n + x.sales_amount_minor, 0),
          })
        }
        const data = {
          context: ctx,
          from,
          to,
          time_basis: 'simulation_time',
          timezone: 'UTC',
          granularity: 'day',
          coverage: 'RECORDED_EVENTS_ONLY',
          record_count: filtered.length,
          recorded_quantity: filtered.reduce((n, x) => n + x.quantity, 0),
          recorded_sales_amount_minor: filtered.reduce((n, x) => n + x.sales_amount_minor, 0),
          buckets,
        }
        if (!b && control.delaySales) await new Promise((r) => setTimeout(r, control.delaySales))
        return route.fulfill({ json: data })
      }
      const offset = Number(url.searchParams.get('cursor') || 0),
        limit = Number(url.searchParams.get('limit') || 30)
      const data = {
        context: ctx,
        items: filtered.slice(offset, offset + limit),
        next_cursor: offset + limit < filtered.length ? String(offset + limit) : null,
      }
      if (control.detailDelay) await new Promise((r) => setTimeout(r, control.detailDelay))
      return route.fulfill({ json: data })
    }
    if (path.startsWith('plans/')) return route.fulfill({ json: f.plan })
    if (path.endsWith('/timeline')) return route.fulfill({ json: f.timeline })
    if (path.endsWith('/conversations'))
      return route.fulfill({ json: { items: [], next_cursor: null } })
    if (f[path]) return route.fulfill({ json: f[path] })
    return route.fulfill({
      status: 404,
      json: { error: { code: 'TEST_UNKNOWN_READ', message: path } },
    })
  })
  return control
}
