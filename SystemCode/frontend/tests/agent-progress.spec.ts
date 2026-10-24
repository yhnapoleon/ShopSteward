import { test, expect } from '@playwright/test'
import { applyProgressEvent, runTools } from '../app/utils/agent-progress'
import type { Schema } from '../app/types/models'
const run = () =>
  ({
    id: 'run-one',
    status: 'RUNNING',
    progress_seq: 1,
    activity: [],
    tools: [],
  }) as unknown as Schema<'RunView'>
const activity = (status = 'RUNNING', attempt = 1) => ({
  invocation_id: 'read-1',
  tool: 'get_dashboard',
  status,
  attempt,
  started_at: '2026-09-08T08:00:00Z',
  finished_at: status === 'RUNNING' ? null : '2026-09-08T08:00:01Z',
  duration_ms: status === 'RUNNING' ? null : 1000,
  error_code: null,
  references: [],
})
const event = (seq: number, type: string, values: Record<string, unknown>) => ({
  schema_version: 1,
  event_id: 'run-one:' + seq,
  run_id: 'run-one',
  seq,
  type,
  invocation_id: 'read-1',
  payload: values,
})

test('实时进度：重复不会重播，缺口不跳过，同名调用保留身份', () => {
  const r = run(),
    start = event(2, 'tool.started', { activity: activity() })
  expect(applyProgressEvent(r, start)).toBe('applied')
  expect(runTools(r)[0]!.status).toBe('RUNNING')
  expect(applyProgressEvent(r, start)).toBe('duplicate')
  expect(
    applyProgressEvent(r, event(4, 'tool.completed', { activity: activity('SUCCEEDED') })),
  ).toBe('gap')
  expect(runTools(r)[0]!.status).toBe('RUNNING')
  expect(
    applyProgressEvent(r, event(3, 'tool.completed', { activity: activity('SUCCEEDED') })),
  ).toBe('applied')
  const another = event(4, 'tool.started', { activity: { ...activity(), invocation_id: 'read-2' } })
  another.invocation_id = 'read-2'
  expect(applyProgressEvent(r, another)).toBe('applied')
  expect(runTools(r)).toHaveLength(2)
  expect(r.status).toBe('RUNNING')
})
test('实时进度：旧任务和无效活动不会改当前任务', () => {
  const r = run()
  expect(
    applyProgressEvent(r, {
      ...event(2, 'tool.started', { activity: activity() }),
      run_id: 'other',
    }),
  ).toBe('invalid')
  expect(applyProgressEvent(r, event(2, 'tool.completed', { activity: activity() }))).toBe(
    'invalid',
  )
  expect(
    applyProgressEvent(
      r,
      event(2, 'tool.started', { activity: { ...activity(), started_at: 'bad' } }),
    ),
  ).toBe('invalid')
  expect(r.progress_seq).toBe(1)
  expect(runTools(r)).toEqual([])
})
test('实时进度：工具失败与整轮成功分离，恢复保持同一调用的尝试号', () => {
  const r = run()
  applyProgressEvent(r, event(2, 'tool.started', { activity: activity() }))
  applyProgressEvent(r, event(3, 'tool.interrupted', { activity: activity('INTERRUPTED') }))
  applyProgressEvent(r, event(4, 'tool.started', { activity: activity('RUNNING', 2) }))
  applyProgressEvent(r, event(5, 'tool.failed', { activity: activity('FAILED', 2) }))
  applyProgressEvent(
    r,
    event(6, 'run.completed', { status: 'SUCCEEDED', finished_at: '2026-09-08T08:00:02Z' }),
  )
  expect(r.status).toBe('SUCCEEDED')
  expect(runTools(r)[0]!.status).toBe('FAILED')
  expect(runTools(r)[0]!.attempt).toBe(2)
  expect(runTools(r)).toHaveLength(1)
})
test('实时进度：旧后端摘要保持兼容，不推测开始或耗时', () => {
  const r = run()
  delete r.activity
  delete r.progress_seq
  r.tools = [{ tool: 'get_dashboard', invocation_id: 'legacy', ok: true, references: [] }]
  expect(runTools(r)[0]).toMatchObject({ status: 'SUCCEEDED', ok: true })
  expect(runTools(r)[0]!.started_at).toBeUndefined()
  expect(runTools(r)[0]!.duration_ms).toBeUndefined()
})
