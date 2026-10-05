import { test, expect } from '@playwright/test'
import { locale, t } from '../app/i18n'
import { resultFile } from '../app/utils/workResultExport'

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
  expect(output).toContain('现金底线')
  expect(output).toContain('查看来源')
  expect(output).toContain('来源 | store:x')
  expect(resultFile(input, 'csv').text).toContain('"商品"')
})
