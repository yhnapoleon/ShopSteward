import { t, locale } from '../i18n'
export const header = '商品,报价金额,币种,计价单位,每包装件数,最低订购量,MOQ单位,来源'
export const samples = [
  { name: '示例报价_甲.csv', text: header + '\n报价样品甲,120,CNY,箱,12,2,箱,示例供应商报价第1条' },
  { name: '示例报价_乙.csv', text: header + '\n报价样品乙,180,CNY,箱,15,3,箱,示例供应商报价第1条' },
  {
    name: '示例报价_待补充.csv',
    text:
      header + '\n包装报价样品,120,CNY,箱,,2,箱,示例第1条\n按件报价样品,12,CNY,件,,,件,示例第2条',
  },
]
export type QuoteRow = {
  record: number
  product: string
  price: number | null
  pack: number | null
  moq: number | null
  moqUnit: string
  unit: string
  currency: string
  source: string
  unitPrice: number | null
  moqPieces: number | null
  basis: string
}
export type QuoteRule = { version: number; source: string; text: string }
export type QuoteResult = {
  name: string
  rows: QuoteRow[]
  issues: string[]
  rule: QuoteRule | null
}
export function parseCSV(text: string) {
  const rows: string[][] = []
  let row: string[] = [],
    cell = '',
    quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (c === '"') {
      if (quoted && text[i + 1] === '"') {
        cell += '"'
        i++
      } else quoted = !quoted
    } else if (c === ',' && !quoted) {
      row.push(cell.trim())
      cell = ''
    } else if ((c === '\n' || c === '\r') && !quoted) {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(cell.trim())
      if (row.some(Boolean)) rows.push(row)
      row = []
      cell = ''
    } else cell += c
  }
  if (quoted) throw Error('CSV引号没有闭合。')
  row.push(cell.trim())
  if (row.some(Boolean)) rows.push(row)
  return rows
}
export function processQuotes(name: string, text: string, rule: QuoteRule | null): QuoteResult {
  const table = parseCSV(text.replace(/^\uFEFF/, '')),
    cols = table.shift()?.map((column) => quoteColumn(column))
  if (!cols || !['商品', '报价金额', '计价单位'].every((k) => cols.includes(k)))
    throw Error('缺少必要列名，请下载格式模板。')
  if (new Set(cols).size !== cols.length) throw Error('列名重复，不能确定报价字段。')
  if (table.some((row) => row.length > cols.length))
    throw Error('报价行的列数超过表头，请核对CSV格式。')
  if (!table.length || table.length > 100) throw Error('请选择1至100条报价资料。')
  const issues: string[] = [],
    positive = (s: string | undefined) =>
      s && /^\d+(\.\d+)?$/.test(s) && Number.isFinite(Number(s)) && Number(s) > 0 ? Number(s) : null
  const rows = table.map((cells, i) => {
    const a = Object.fromEntries(cols.map((h, i) => [h, cells[i] || ''])),
      record = i + 1,
      price = positive(a['报价金额']),
      pack = positive(a['每包装件数']),
      moq = positive(a['最低订购量']),
      unit = quoteUnit(a['计价单位'] || ''),
      moqUnit = quoteUnit(a['MOQ单位'] || '')
    let unitPrice: number | null = null,
      basis = '缺少计算依据'
    const problem = (t: string) => issues.push(`第${record}条报价：${t}`)
    if (!a['商品']) problem('商品名称缺失。')
    if (price === null) problem('报价金额应为正数。')
    if (!['CNY', '人民币', '元'].includes(a['币种'] || ''))
      problem('币种缺失或不支持，不能直接换算比较。')
    else if (price !== null) {
      if (unit === '件') {
        unitPrice = price
        basis = '原价按件，不再除包装数'
      } else if (['箱', '包'].includes(unit) && pack) {
        unitPrice = price / pack
        basis = `${price}元 ÷ ${pack}件`
      } else problem('计价单位或包装数缺失，不能确定单件价。')
    }
    if (!pack) problem('包装数量缺失。')
    if (!moq || !['件', '箱', '包'].includes(moqUnit)) problem('最低订购量或其单位缺失。')
    if (!a['来源']) problem('供应商来源未提供，仍可按文件记录定位。')
    return {
      record,
      product: a['商品'] || '未命名商品',
      price,
      pack,
      moq,
      unit,
      moqUnit,
      currency: a['币种'] || '',
      source: a['来源'] || '',
      unitPrice,
      basis,
      moqPieces: moq
        ? moqUnit === '件'
          ? moq
          : ['箱', '包'].includes(moqUnit) && pack
            ? moq * pack
            : null
        : null,
    }
  })
  if (rule) rows.sort((a, b) => (a.unitPrice ?? Infinity) - (b.unitPrice ?? Infinity))
  return { name, rows, issues, rule: rule ? { ...rule } : null }
}
function cell(v: unknown) {
  let s = String(v ?? '')
  if (/^[\s\u0000-\u001f]*[=+\-@]|^[\t\r\n]/.test(s)) s = "'" + s
  return '"' + s.replaceAll('"', '""') + '"'
}
export function quoteCSV(r: QuoteResult) {
  return [
    [
      '商品',
      '单件价（元）',
      '原报价',
      '原币种',
      '计价单位',
      '包装件数',
      '最低订购量',
      'MOQ单位',
      'MOQ件数',
      '来源',
      '资料序号',
    ],
    ...r.rows.map((a) => [
      a.product,
      a.unitPrice ?? t('未确定'),
      a.price,
      a.currency,
      t(a.unit),
      a.pack,
      a.moq,
      t(a.moqUnit),
      a.moqPieces,
      a.source,
      a.record,
    ]),
  ]
    .map((r, i) => r.map((value) => cell(i === 0 ? t(value) : value)).join(','))
    .join('\n')
}
export function downloadFile(
  name: string,
  text: string,
  mime = 'text/plain;charset=utf-8',
  bom = true,
) {
  const url = URL.createObjectURL(new Blob([(bom ? '\ufeff' : '') + text], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const englishHeaders = [
  'Product',
  'Quote amount',
  'Currency',
  'Pricing unit',
  'Units per pack',
  'Minimum order',
  'MOQ unit',
  'Source',
]
function quoteColumn(value: string) {
  const index = englishHeaders.findIndex((key) => key.toLowerCase() === value.trim().toLowerCase())
  return index < 0 ? value : header.split(',')[index]!
}
function quoteUnit(value: string) {
  return (
    (
      {
        unit: '件',
        units: '件',
        piece: '件',
        pieces: '件',
        box: '箱',
        boxes: '箱',
        pack: '包',
        packs: '包',
      } as Record<string, string>
    )[value.toLowerCase()] || value
  )
}
export function localizedSamples() {
  if (locale.value !== 'en') return samples
  const head = englishHeaders.join(',') + '\n'
  return [
    {
      name: 'sample-quote-A.csv',
      text: head + 'Sample A,120,CNY,box,12,2,box,Sample supplier quote 1',
    },
    {
      name: 'sample-quote-B.csv',
      text: head + 'Sample B,180,CNY,box,15,3,box,Sample supplier quote 1',
    },
    {
      name: 'sample-quote-incomplete.csv',
      text:
        head +
        'Pack sample,120,CNY,box,,2,box,Sample record 1\nUnit sample,12,CNY,unit,,,unit,Sample record 2',
    },
  ]
}
