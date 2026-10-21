import { test, expect } from '@playwright/test'
import { locale, t } from '../app/i18n'
import { resultFile, resultTitle } from '../app/utils/workResultExport'
import { describeTool, sourceLabel } from '../app/utils/agent'

test.afterEach(() => {
  locale.value = 'zh-CN'
})
test('translated templates preserve original product names, identifiers and spaces', () => {
  locale.value = 'en'
  expect(t('库存 · 补货数量试算')).toBe('库存 · Restocking quantity trial')
  expect(t('现  金 · 补货数量试算')).toBe('现  金 · Restocking quantity trial')
})
test('external result assumptions, cells and source labels are not rewritten', () => {
  locale.value = 'en'
  const input: any = {
    result: {
      kind: 'analysis',
      title: '库存',
      content: '现金',
      columns: ['商品'],
      rows: [['采购']],
      assumptions: ['现金底线'],
      references: [{ type: 'store', id: 'x', label: '来源' }],
      provenance: { result_id: 'r', result_version: 1, limitations: ['查看来源'] },
    },
    is_latest_result: true,
  }
  const output = resultFile(input, 'txt').text
  expect(resultTitle(input.result)).toBe('库存')
  expect(output.split('\n')[0]).toBe('库存')
  expect(output).toContain('现金底线')
  expect(output).toContain('查看来源')
  expect(output).toContain('来源 | store:x')
  expect(resultFile(input, 'csv').text).toContain('"商品"')
})
test("the backend's own result title follows the language", () => {
  locale.value = 'en'
  const input: any = {
    result: { kind: 'answer', title: '事项处理结果', content: '现金', provenance: {} },
    is_latest_result: true,
  }
  expect(resultTitle(input.result)).toBe('Request result')
  const output = resultFile(input, 'txt').text
  expect(output.split('\n')[0]).toBe('Request result')
  expect(output).toContain('Title：Request result')
})
test('Agent tool records and their sources read in English', () => {
  locale.value = 'en'
  // The Mission Agent's tools (backend agent_bridge/tools.py and document_evidence.py), plus one
  // the page does not know, which falls back to a generic step.
  const tools = [
    'get_dashboard',
    'get_mission',
    'get_plan',
    'evaluate_plan',
    'revise_plan',
    'search_documents',
    'read_document_evidence',
    'memory_edit',
    'request_check',
    'read_sales_summary',
    'read_timeline',
    'read_experiences',
    'get_action',
    'get_forecast',
    'get_recovery_cases',
    'get_recovery_case',
    'analyze_recovery_case',
    'some_future_tool',
  ]
  const han = /[㐀-鿿]/
  for (const tool of tools) {
    const { title, done, kind } = describeTool(tool)
    for (const text of [title, done, kind]) expect(t(text), `${tool}: ${text}`).not.toMatch(han)
  }
  expect(t(describeTool('get_plan').title)).toBe('Read current plan')
  expect(t(describeTool('get_dashboard').title)).toBe('Check cash, stock and arrivals')
  const sources = [null, { chunk_id: 'c' }, { type: 'plan' }, { type: 'action' }, { type: 'x' }]
  for (const source of sources) expect(t(sourceLabel(source))).not.toMatch(han)
})
