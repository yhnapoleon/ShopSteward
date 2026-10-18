import { joinText, t } from '~/i18n'
import type { Schema } from '~/types/models'
import { money, number, reasonLabel } from '~/utils/presentation'
import type { Block, CatalogProps, EvidenceItem, Surface } from './types'
import { validateSurface } from './validate'

// Surfaces derived from the structured results the backend returns today (redesign §9). The same
// result always gives the same blocks, and every figure is the backend's own, formatted for the
// current language. Derived surfaces are built here from fields the backend already validated
// (content ≤ 16000 characters, ≤ 12 columns, ≤ 100 rows, ≤ 20 assumptions and sources), so they
// are not cut to the limits that guard external surfaces: nothing the result holds is hidden.

type Result = Schema<'WorkResult'>
type Outcome = Schema<'BusinessOutcome'>
type Comparison = Schema<'PlanComparison'>
type Candidate = Schema<'Candidate'>

/** A stable key for any JSON value: the same content gives the same key in every language. */
export function contentKey(value: unknown): string {
  let text = ''
  try {
    text = JSON.stringify(value) ?? ''
  } catch {
    text = String(value)
  }
  let hash = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return (hash >>> 0).toString(36) + '-' + text.length.toString(36)
}

/** Evidence folds hold up to 20 entries each; a longer list continues in a second fold. */
function evidence(items: EvidenceItem[]): Block[] {
  const blocks: Block[] = []
  for (let start = 0; start < items.length; start += 20)
    blocks.push({
      component: 'EvidenceList',
      props: {
        label: t(start ? '依据与假设（续）' : '依据与假设'),
        items: items.slice(start, start + 20),
      },
    })
  return blocks
}

/** The four figures of the recommended candidate in a quantity calculation. */
function cost(recommended: Candidate): Block {
  return {
    component: 'MetricRow',
    props: {
      label: t('推荐候选的代价'),
      items: [
        { label: t('本次推荐数量'), value: number(recommended.quantity), unit: t('件') },
        { label: t('预计支出'), value: t(money(recommended.spend_minor)) },
        { label: t('可用现金剩余'), value: t(money(recommended.cash_after_minor)) },
        { label: t('按时到货后缺口'), value: number(recommended.shortage_qty), unit: t('件') },
      ],
    },
  }
}

/**
 * A work result as blocks: for a quantity calculation the recommended candidate's cost, then the
 * explanation, the candidate table (recommended row highlighted) and the evidence; for other
 * results the text, any table and the evidence. Quotations keep their own workspace (null).
 */
export function fromWorkResult(result: Result): Surface | null {
  if (result.kind === 'quotation') return null
  const calculation = result.calculation
  // Words the system wrote for a calculation are translated; anyone else's stay as written.
  const own = (text: string) => (calculation ? t(text) : text)
  const blocks: Block[] = []
  const recommended = calculation?.candidates.find(
    (c) => c.id === calculation.recommended_candidate_id,
  )
  if (recommended) blocks.push(cost(recommended))
  const content = calculation
    ? result.content
        .split('\n')
        .map((line) => t(line))
        .join('\n')
    : result.content
  if (content.trim()) blocks.push({ component: 'Text', props: { markdown: content } })
  if (result.columns?.length) {
    const highlight = calculation?.recommended_candidate_id
      ? calculation.candidates.findIndex((c) => c.id === calculation.recommended_candidate_id)
      : -1
    blocks.push({
      component: 'PlanComparison',
      props: {
        columns: result.columns.map(own),
        rows: (result.rows || []).map((row) => row.map(own)),
        highlightIndex: highlight >= 0 ? highlight : undefined,
      },
    })
  }
  blocks.push(
    ...evidence([
      ...(result.assumptions || []).map((a) => ({ label: own(a) })),
      ...(result.references || []).map((r) => ({ label: own(r.label), type: t(r.type), id: r.id })),
      ...(result.provenance?.limitations || []).map((l) => ({ label: own(l) })),
    ]),
  )
  return blocks.length ? { version: 1, blocks } : null
}

/** A result's own surface when it carries a valid one; otherwise the derived surface. */
export function resultSurface(result: Result): Surface | null {
  const attached = (result as Result & { surface?: unknown }).surface
  return (attached != null ? validateSurface(attached) : null) ?? fromWorkResult(result)
}

const chosen = (p: Comparison) => p.candidates.find((c) => c.id === p.recommended_candidate_id)
const units = (n: number) => joinText([number(n), t('件')], ' ')

/** One plan's candidates as a comparison table with its recommendation marked. */
function comparison(p: Comparison, title: string, label: string): Block {
  const highlight = p.candidates.findIndex((c) => c.id === p.recommended_candidate_id)
  const props: CatalogProps['PlanComparison'] = {
    title,
    label,
    columns: [t('补货'), t('支出'), t('采购后现金'), t('预计缺货'), t('约束判断')],
    rows: p.candidates.map((c) => [
      c.id === p.recommended_candidate_id
        ? joinText([units(c.quantity), t('· 推荐')], ' ')
        : units(c.quantity),
      t(money(c.spend_minor)),
      t(money(c.cash_after_minor)),
      units(c.shortage_qty),
      c.feasible
        ? t('满足约束')
        : c.rejection_reasons.map((r) => t(reasonLabel(r))).join(t('、')),
    ]),
    highlightIndex: highlight >= 0 ? highlight : undefined,
  }
  return { component: 'PlanComparison', props }
}

/**
 * An Agent business outcome: the recommended quantity, cash after purchase and shortage before →
 * after, then the resulting candidates. `before: true` adds the original plan's table first.
 */
export function fromOutcome(outcome: Outcome, options: { before?: boolean } = {}): Surface | null {
  const { before, after } = outcome
  if (outcome.availability !== 'available' || !before || !after) return null
  const trial = outcome.kind === 'evaluation'
  const was = chosen(before),
    now = chosen(after)
  const change = (from: string, to: string) => `${from} → ${to}`
  const blocks: Block[] = [
    {
      component: 'MetricRow',
      props: {
        label: t(trial ? '试算前后对比' : '修订前后对比'),
        items: [
          {
            label: t('推荐补货'),
            value: change(was ? number(was.quantity) : '—', now ? number(now.quantity) : '—'),
            unit: t('件'),
          },
          {
            label: t('采购后现金'),
            value: change(
              was ? t(money(was.cash_after_minor)) : '—',
              now ? t(money(now.cash_after_minor)) : '—',
            ),
          },
          {
            label: t('预计缺货'),
            value: change(
              was ? number(was.shortage_qty) : '—',
              now ? number(now.shortage_qty) : '—',
            ),
            unit: t('件'),
          },
        ],
      },
    },
  ]
  if (options.before) blocks.push(comparison(before, t('原方案'), t('原方案候选比较')))
  blocks.push(comparison(after, t(trial ? '假设结果' : '修订方案'), t('结果候选比较')))
  return { version: 1, blocks }
}
