import {
  FIELD_KINDS,
  NEXT_STEP_TARGETS,
  type Block,
  type CatalogName,
  type CatalogProps,
  type ClarificationField,
  type FieldKind,
  type NextStepTarget,
} from './types'

// The trusted component catalog (workspace redesign §9). Each entry rebuilds its props from the
// declared fields only; anything undeclared, nested, oversized or malformed never reaches a
// component. A block that breaks its own limits is dropped whole rather than shown in part.

/** What is left of one surface's text allowance, in UTF-8 bytes. */
export type Budget = { bytes: number }
/** Thrown when a surface's text exceeds its allowance; the whole surface is then unusable. */
export class OverBudget extends Error {}
class Invalid extends Error {}
const fail = (): never => {
  throw new Invalid()
}

const encoder = new TextEncoder()
// Tags, comments, doctypes and <scheme:…> / <user@host> autolinks all look like `<x…>`.
const tags = /<\/?[a-z!][^>]*>/gi
const controls = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g

function spend(budget: Budget, text: string) {
  budget.bytes -= encoder.encode(text).length
  if (budget.bytes < 0) throw new OverBudget()
}
function record(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const proto = Object.getPrototypeOf(value)
  return proto === Object.prototype || proto === null
}
/** Blocks never contain blocks: any object that looks like one makes the block invalid. */
function noBlocks(value: unknown, depth = 0): void {
  if (depth > 3) return
  if (Array.isArray(value)) value.forEach((item) => noBlocks(item, depth + 1))
  else if (record(value)) {
    if ('component' in value || 'blocks' in value) fail()
    Object.values(value).forEach((item) => noBlocks(item, depth + 1))
  }
}
/** Plain text: no markup, no control characters, within its length. */
function plain(value: unknown, max: number, budget: Budget): string {
  if (typeof value !== 'string') return fail()
  const clean = value.replace(controls, '').replace(tags, '').trim()
  if (!clean || clean.length > max) fail()
  spend(budget, clean)
  return clean
}
function optional(value: unknown, max: number, budget: Budget): string | undefined {
  return value === undefined || value === null || value === ''
    ? undefined
    : plain(value, max, budget)
}
/** A figure may arrive as a finite number; it is shown exactly as given. */
function figure(value: unknown, max: number, budget: Budget): string {
  return plain(typeof value === 'number' && Number.isFinite(value) ? String(value) : value, max, budget)
}
/** A whole number of units, cents or rows; never negative. */
function count(value: unknown, max = 1_000_000_000): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0 || value > max) fail()
  return value as number
}
function list(value: unknown, max: number): unknown[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > max) fail()
  return value as unknown[]
}
function entry(value: unknown): Record<string, unknown> {
  if (!record(value)) fail()
  return value as Record<string, unknown>
}
/**
 * Markdown from outside the frontend keeps its words but loses everything that could fetch or
 * navigate: images become their alt text, links their label, and HTML is removed. In-site moves
 * belong to NextStep, which can only name an existing dialog or view.
 */
export function readableMarkdown(value: unknown, budget: Budget, max = 16 * 1024): string {
  if (typeof value !== 'string') return fail()
  const clean = value
    .replace(controls, '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^ {0,3}\[[^\]]+\]:\s*\S.*$/gm, '')
    .replace(tags, '')
    .trim()
  if (!clean || clean.length > max) fail()
  spend(budget, clean)
  return clean
}

const KEY = /^[A-Za-z][A-Za-z0-9_-]{0,39}$/

type Sanitizers = {
  [K in CatalogName]: (props: Record<string, unknown>, budget: Budget) => CatalogProps[K]
}
export const CATALOG: Sanitizers = {
  MetricRow: (p, b) => ({
    label: optional(p.label, 200, b),
    items: list(p.items, 6).map((raw) => {
      const item = entry(raw)
      return {
        label: plain(item.label, 200, b),
        value: figure(item.value, 80, b),
        unit: optional(item.unit, 16, b),
        hint: optional(item.hint, 200, b),
      }
    }),
  }),
  PlanComparison: (p, b) => {
    const columns = list(p.columns, 8).map((c) => plain(c, 200, b))
    const rows = list(p.rows, 100).map((raw) => {
      const row = list(raw, 8)
      if (row.length !== columns.length) fail()
      // A cell may be empty: an unknown value stays unknown instead of being guessed.
      return row.map((cell) => (cell === '' ? '' : figure(cell, 1000, b)))
    })
    const highlight = p.highlightIndex === undefined ? undefined : count(p.highlightIndex)
    if (highlight !== undefined && highlight >= rows.length) fail()
    return {
      title: optional(p.title, 200, b),
      label: optional(p.label, 200, b),
      columns,
      rows,
      highlightIndex: highlight,
    }
  },
  EvidenceList: (p, b) => ({
    label: optional(p.label, 200, b),
    items: list(p.items, 20).map((raw) => {
      const item = entry(raw)
      return {
        label: plain(item.label, 200, b),
        type: optional(item.type, 40, b),
        id: optional(item.id, 128, b),
      }
    }),
  }),
  DemandChange: (p, b) => ({
    before: count(p.before),
    after: count(p.after),
    reason: optional(p.reason, 200, b),
    keep: p.keep === undefined ? undefined : count(p.keep),
    gap: p.gap === undefined ? undefined : count(p.gap),
  }),
  QuoteTable: (p, b) => ({
    rows: list(p.rows, 100).map((raw) => {
      const row = entry(raw)
      return {
        product: plain(row.product, 200, b),
        unitPrice: optional(row.unitPrice, 80, b),
        pack: optional(row.pack, 80, b),
        minimumOrder: optional(row.minimumOrder, 80, b),
        source: optional(row.source, 200, b),
      }
    }),
  }),
  NextStep: (p, b) => ({
    actions: list(p.actions, 4).map((raw) => {
      const action = entry(raw)
      if (!NEXT_STEP_TARGETS.includes(action.open as NextStepTarget)) fail()
      return { label: plain(action.label, 40, b), open: action.open as NextStepTarget }
    }),
  }),
  ClarificationForm: (p, b) => {
    const fields: ClarificationField[] = list(p.fields, 6).map((raw) => {
      const field = entry(raw)
      if (typeof field.key !== 'string' || !KEY.test(field.key)) fail()
      if (!FIELD_KINDS.includes(field.kind as FieldKind)) fail()
      return {
        key: field.key as string,
        label: plain(field.label, 80, b),
        kind: field.kind as FieldKind,
      }
    })
    if (new Set(fields.map((f) => f.key)).size !== fields.length) fail()
    return { fields }
  },
  Text: (p, b) => ({ markdown: readableMarkdown(p.markdown, b) }),
}

const READABLE = ['markdown', 'text', 'content', 'body', 'title', 'label', 'summary', 'description']

/**
 * One block from outside the frontend. A known component keeps only its declared, valid props;
 * an unknown one becomes Text when it carries readable words, otherwise it is dropped.
 */
export function sanitizeBlock(raw: unknown, budget: Budget): Block | null {
  if (!record(raw) || typeof raw.component !== 'string') return null
  const props = raw.props === undefined ? {} : raw.props
  if (!record(props)) return null
  const name = raw.component
  // Text spent on a block that is then dropped goes back to the allowance.
  const allowance = budget.bytes
  try {
    if (Object.hasOwn(CATALOG, name)) {
      noBlocks(props)
      const sanitize = CATALOG[name as CatalogName] as (
        props: Record<string, unknown>,
        budget: Budget,
      ) => Block['props']
      return { component: name, props: sanitize(props, budget) } as Block
    }
    const words = READABLE.map((key) => props[key])
      .filter((value): value is string => typeof value === 'string' && !!value.trim())
      .join('\n\n')
    return words ? { component: 'Text', props: { markdown: readableMarkdown(words, budget) } } : null
  } catch (error) {
    if (error instanceof OverBudget) throw error
    budget.bytes = allowance
    return null
  }
}
