import type { Schema } from '~/types/models'
import type { ToolRecord } from './agent'

type Activity = Schema<'ToolActivityView'>
type Run = Schema<'RunView'>
const states = ['RUNNING', 'SUCCEEDED', 'FAILED', 'INTERRUPTED'] as const
const object = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)
const date = (v: unknown) => typeof v === 'string' && Number.isFinite(Date.parse(v))
export function activityRecord(value: unknown): Activity | null {
  if (
    !object(value) ||
    typeof value.invocation_id !== 'string' ||
    typeof value.tool !== 'string' ||
    !states.includes(value.status as Activity['status']) ||
    !Number.isSafeInteger(value.attempt) ||
    Number(value.attempt) < 1 ||
    !date(value.started_at)
  )
    return null
  if (value.finished_at != null && !date(value.finished_at)) return null
  if (
    value.duration_ms != null &&
    (!Number.isSafeInteger(value.duration_ms) || Number(value.duration_ms) < 0)
  )
    return null
  return {
    invocation_id: value.invocation_id,
    tool: value.tool,
    status: value.status as Activity['status'],
    attempt: Number(value.attempt),
    started_at: String(value.started_at),
    finished_at: value.finished_at == null ? null : String(value.finished_at),
    duration_ms: value.duration_ms == null ? null : Number(value.duration_ms),
    error_code: typeof value.error_code === 'string' ? value.error_code : null,
    references: Array.isArray(value.references) ? value.references.filter(object) : [],
  }
}
export function runTools(run: Run | null): ToolRecord[] {
  const records = new Map<string, ToolRecord>()
  for (const raw of run?.tools || []) {
    if (!object(raw) || typeof raw.invocation_id !== 'string' || typeof raw.tool !== 'string')
      continue
    const ok = typeof raw.ok === 'boolean' ? raw.ok : null
    records.set(raw.invocation_id, {
      invocation_id: raw.invocation_id,
      tool: raw.tool,
      ok,
      status: ok === true ? 'SUCCEEDED' : ok === false ? 'FAILED' : undefined,
      references: Array.isArray(raw.references) ? raw.references : [],
    })
  }
  for (const raw of run?.activity || []) {
    const a = activityRecord(raw)
    if (a)
      records.set(a.invocation_id, {
        ...a,
        ok: a.status === 'SUCCEEDED' ? true : a.status === 'FAILED' ? false : null,
        references: a.references || [],
      })
  }
  return [...records.values()]
}
const runStatuses: Record<string, Run['status']> = {
  'run.queued': 'QUEUED',
  'run.started': 'RUNNING',
  'run.waiting_input': 'WAITING_INPUT',
  'run.completed': 'SUCCEEDED',
  'run.failed': 'FAILED',
  'run.cancelled': 'CANCELLED',
}
const toolStatuses: Record<string, Activity['status']> = {
  'tool.started': 'RUNNING',
  'tool.completed': 'SUCCEEDED',
  'tool.failed': 'FAILED',
  'tool.interrupted': 'INTERRUPTED',
}
export function applyProgressEvent(
  run: Run,
  value: unknown,
): 'applied' | 'duplicate' | 'gap' | 'invalid' {
  if (
    !object(value) ||
    value.schema_version !== 1 ||
    value.run_id !== run.id ||
    !Number.isSafeInteger(value.seq) ||
    Number(value.seq) < 1 ||
    typeof value.type !== 'string' ||
    !object(value.payload)
  )
    return 'invalid'
  const seq = Number(value.seq),
    current = run.progress_seq || 0
  if (seq <= current) return 'duplicate'
  if (seq !== current + 1) return 'gap'
  if (toolStatuses[value.type]) {
    const a = activityRecord(value.payload.activity)
    if (!a || a.invocation_id !== value.invocation_id || a.status !== toolStatuses[value.type])
      return 'invalid'
    const rows = new Map((run.activity || []).map((a) => [a.invocation_id, a]))
    rows.set(a.invocation_id, a)
    run.activity = [...rows.values()]
  } else if (runStatuses[value.type]) {
    if (value.payload.status !== runStatuses[value.type]) return 'invalid'
    run.status = runStatuses[value.type]!
    if (value.type === 'run.waiting_input') {
      run.question = typeof value.payload.question === 'string' ? value.payload.question : null
      run.interrupt_id =
        typeof value.payload.interrupt_id === 'string' ? value.payload.interrupt_id : null
    }
    if (date(value.payload.finished_at)) run.finished_at = String(value.payload.finished_at)
    if (typeof value.payload.error_code === 'string') run.error_code = value.payload.error_code
  } else return 'invalid'
  run.progress_seq = seq
  return 'applied'
}
