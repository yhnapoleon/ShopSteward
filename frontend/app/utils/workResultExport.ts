import { t } from '../i18n'
import type { Schema } from '~/types/models'

export type ResultFileFormat = 'txt' | 'csv' | 'json'
const kinds: Record<string, string> = {
  answer: '咨询答复',
  analysis: '分析',
  forecast: '预测',
  quotation: '报价整理',
  brief: '简报',
}
const missing = '未记录'

function rawMetadata(value: Schema<'WorkResultExport'>): [string, string][] {
  const r = value.result,
    p = r.provenance
  return [
    ['结果ID', p?.result_id || missing],
    ['结果版本', String(p?.result_version ?? missing)],
    ['事项ID', p?.work_id || missing],
    ['发布时事项版本', String(p?.work_version ?? missing)],
    ['生成时间', p?.generated_at || missing],
    ['业务截至', p?.data_as_of || missing],
    ['业务状态版本', String(p?.state_version ?? missing)],
    ['结果类型', r.calculation ? '假设试算，不是采购方案' : kinds[r.kind] || r.kind],
    ['经营来源', p?.source_type === 'simulation' ? '合成模拟环境' : p?.source_type || missing],
    ['币种', p?.currency || missing],
    ['标题', r.title],
    ['正文', r.content],
    ['输入假设', (r.assumptions || []).join('\n') || '未提供'],
    [
      '来源引用',
      (r.references || [])
        .map(
          (ref) =>
            `${ref.label} | ${ref.type}:${ref.id} | 版本 ${p?.reference_versions?.[ref.type + ':' + ref.id] ?? missing}`,
        )
        .join('\n') || '未提供',
    ],
    [
      '适用性',
      [
        value.is_latest_result ? '此事项最近一次结果' : '此事项历史结果',
        ...(value.stale_reasons || []),
        ...(value.demonstration ? ['模拟处理响应，非真实Agent分析'] : []),
      ].join('\n'),
    ],
    ['局限', [...(p?.limitations || []), '采购和到货以实际业务回执为准。'].join('\n')],
    ...(r.calculation
      ? ([
          ['计算规则版本', r.calculation.rule_version],
          ['输入快照hash', r.calculation.input_hash],
          ['报价版本', r.calculation.input.offer.offer_version],
          ['业务需求版本', r.calculation.input.forecast_version || '用户独立假设'],
          ['预测证据ID', r.calculation.input.forecast_id || '用户独立假设'],
          [
            '需求提供者',
            r.calculation.input.forecast_provider === 'v6'
              ? 'v6模型预测'
              : '经营需求投影或用户假设',
          ],
          ['表格单位', '金额为人民币元，数量为件；JSON原始金额字段为整数分。'],
        ] as [string, string][])
      : []),
  ]
}

export function resultMetadata(value: Schema<'WorkResultExport'>): [string, string][] {
  const r = value.result
  return rawMetadata(value).map(([key, content]) => {
    if (['标题', '正文', '输入假设'].includes(key) && !r.calculation) return [t(key), content]
    if (key === '局限' && !r.calculation)
      return [
        t(key),
        [...(r.provenance?.limitations || []), t('采购和到货以实际业务回执为准。')].join('\n'),
      ]
    if (key === '来源引用')
      return [
        t(key),
        (r.references || [])
          .map((ref) =>
            t('{0} | {1}:{2} | 版本 {3}', [
              r.calculation ? t(ref.label) : ref.label,
              ref.type,
              ref.id,
              r.provenance?.reference_versions?.[ref.type + ':' + ref.id] ?? t(missing),
            ]),
          )
          .join('\n') || t('未提供'),
      ]
    const systemFields = ['结果类型', '经营来源', '适用性', '表格单位', '需求提供者']
    const localize =
      (!!r.calculation && ['标题', '正文', '输入假设', '局限'].includes(key)) ||
      systemFields.includes(key) ||
      content === missing ||
      content === '用户独立假设'
    return [
      t(key),
      localize
        ? content
            .split('\n')
            .map((line) => t(line))
            .join('\n')
        : content,
    ]
  })
}

export function csvCell(value: string) {
  // Quoting alone does not stop spreadsheet formulas. Preserve arbitrary text as text.
  const safe = /^[\s\u0000-\u001f]*[=+\-@]|^[\t\r\n]/.test(value) ? "'" + value : value
  return '"' + safe.replace(/"/g, '""') + '"'
}

export function resultFile(value: Schema<'WorkResultExport'>, format: ResultFileFormat) {
  const r = value.result,
    metadata = resultMetadata(value)
  const name = t('事项结果-{0}-v{1}.{2}', [
    r.provenance?.result_id || t('历史'),
    r.provenance?.result_version || 1,
    format,
  ])
  if (format === 'json')
    return { name, mime: 'application/json;charset=utf-8', text: JSON.stringify(value, null, 2) }
  if (format === 'csv') {
    const columns = (r.columns || []).map((column) => (r.calculation ? t(column) : column))
    const rows = r.rows?.length ? r.rows : [columns.map(() => '')]
    const records = [
      [...columns, ...metadata.map(([key]) => key)],
      ...rows.map((row) => [
        ...row.map((cell) => (r.calculation ? t(cell) : cell)),
        ...metadata.map(([, text]) => text),
      ]),
    ]
    return {
      name,
      mime: 'text/csv;charset=utf-8',
      text: records.map((row) => row.map(csvCell).join(',')).join('\r\n'),
    }
  }
  return {
    name,
    mime: 'text/plain;charset=utf-8',
    text: [
      r.calculation ? t(r.title) : r.title,
      '',
      ...metadata.map(([key, value]) => `${key}：${value}`),
      '',
      ...(r.columns?.length
        ? [
            t('比较表'),
            r.columns.map((cell) => (r.calculation ? t(cell) : cell)).join('\t'),
            ...(r.rows || []).map((row) =>
              row.map((cell) => (r.calculation ? t(cell) : cell)).join('\t'),
            ),
          ]
        : []),
    ].join('\n'),
  }
}
