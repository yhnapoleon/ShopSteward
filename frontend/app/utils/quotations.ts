import { locale } from '../i18n'
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
