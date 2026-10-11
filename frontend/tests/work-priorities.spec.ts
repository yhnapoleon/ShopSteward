import { test, expect } from '@playwright/test'
import { resultFile, csvCell } from '../app/utils/workResultExport'
import { newerWork, workPresentation } from '../app/utils/workPresentation'

test('旧列表迟到不能覆盖更新的采购状态；输入版本与业务观察独立比较', () => {
  const old = {
    id: 'w',
    version: 5,
    mission_id: 'm',
    status: 'RESULT_READY',
    business: { observed_at: '2026-09-12T00:00:00Z', code: 'FOLLOWING' },
  } as any
  const current = {
    ...old,
    version: 4,
    business: { observed_at: '2026-09-12T00:00:02Z', code: 'UNKNOWN' },
  }
  expect(newerWork(current, old).version).toBe(5)
  expect(newerWork(current, old).business?.code).toBe('UNKNOWN')
  expect(newerWork(old, current).business?.code).toBe('UNKNOWN')
})

test('待补信息不能遮蔽结果不明采购，审批提示到期后需要重查', () => {
  const item = {
    status: 'WAITING_INPUT',
    question: '活动是哪天？',
    business: {
      code: 'UNKNOWN',
      label: '采购结果待核实',
      detail: '先核实',
      action_label: '查看采购回执',
      priority: 0,
      tone: 'amber',
    },
  } as any
  expect(workPresentation(item).label).toBe('采购结果待核实')
  const pending = {
    ...item,
    business: {
      ...item.business,
      code: 'PENDING_APPROVAL',
      can_confirm: true,
      valid_until: '2026-09-12T01:00:00Z',
    },
  }
  expect(workPresentation(pending, Date.parse('2026-09-12T01:00:00Z')).label).toBe('方案待重新核对')
})

test('导出完整保留中文、空值、负数、小数、假设及模拟标识', () => {
  const value = {
    result: {
      kind: 'analysis',
      title: '中文结果',
      content: '条件说明',
      columns: ['备注', '金额（元）'],
      rows: [
        ['含逗号,及"引号"\n换行', '-12.50'],
        ['', '0.00'],
      ],
      assumptions: ['不能把待结算当现金'],
      references: [],
      provenance: {
        result_id: 'r1',
        result_version: 1,
        work_id: 'w1',
        work_version: 3,
        generated_at: '2026-09-12T00:00:00Z',
        data_as_of: null,
        state_version: null,
        currency: 'CNY',
        source_type: 'simulation',
        limitations: ['尚无业务快照'],
      },
    },
    demonstration: true,
    current_work_version: 7,
    is_latest_result: false,
    stale_reasons: ['经营状态已变化'],
  } as any
  const text = resultFile(value, 'txt'),
    csv = resultFile(value, 'csv')
  expect(text.text).toContain('业务截至：未记录')
  expect(text.text).toContain('-12.50')
  expect(text.text).toContain('不能把待结算当现金')
  expect(text.text).toContain('模拟处理响应')
  expect(csv.text).toContain('"含逗号,及""引号""\n换行"')
  expect(csv.text).toContain('"\'-12.50"')
  expect(csv.text).toContain('"","0.00"')
  expect(csv.name).toBe('事项结果-r1-v1.csv')
  expect(resultFile(value, 'txt')).toEqual(text)
})

test('CSV 引号不能代替公式防护，带空白或控制字符的公式仍按文本导出', () => {
  for (const value of ['=SUM(1,2)', ' +CMD', '\t@SUM(A1)', '\r-1', '@example'])
    expect(csvCell(value).startsWith('"\'')).toBe(true)
  expect(csvCell('普通文本')).toBe('"普通文本"')
})
