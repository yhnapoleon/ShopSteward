import { test, expect } from '@playwright/test'
import { locale, t } from '../app/i18n'
import { header, processQuotes, quoteCSV } from '../app/utils/quotations'
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
test('bilingual duplicate columns and excess cells cannot silently overwrite quotes', () => {
  expect(() =>
    processQuotes(
      'x.csv',
      'Product,商品,Quote amount,Pricing unit,Currency\nA,B,120,box,CNY',
      null,
    ),
  ).toThrow()
  expect(() =>
    processQuotes('x.csv', 'Product,Quote amount,Pricing unit,Currency\nA,120,box,CNY,extra', null),
  ).toThrow()
})
test('quote export keeps unknowns localized and blocks formulas after whitespace', () => {
  locale.value = 'en'
  const result = processQuotes('x.csv', header + '\nA,120,CNY,箱,,2,箱,source', null)
  result.rows[0]!.product = '\t=SUM(1,2)'
  expect(quoteCSV(result)).toContain('Undetermined')
  expect(quoteCSV(result)).toContain('"\'\t=SUM(1,2)"')
})
