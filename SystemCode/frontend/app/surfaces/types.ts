// Dynamic surfaces (workspace redesign §9): a structured result shown as a short list of trusted
// components. A surface only presents values the backend already produced; no block can approve,
// purchase or change business data, and none carries HTML, scripts, remote resources or URLs.

/** Existing dialogs and views a NextStep block may open; never the approval dialog. */
export const NEXT_STEP_TARGETS = [
  'evidence',
  'compare',
  'receipt',
  'mission',
  'simulation',
  'quote',
  'documents',
  'overview',
  'facts',
] as const
export type NextStepTarget = (typeof NEXT_STEP_TARGETS)[number]
/** Targets that are page views (`?view=…`); the others open an existing dialog. */
export const VIEW_TARGETS: readonly NextStepTarget[] = ['documents', 'overview']

export const FIELD_KINDS = ['number', 'date', 'range', 'text'] as const
export type FieldKind = (typeof FIELD_KINDS)[number]

export type MetricItem = { label: string; value: string; unit?: string; hint?: string }
export type EvidenceItem = { label: string; type?: string; id?: string }
export type QuoteRow = {
  product: string
  unitPrice?: string
  pack?: string
  minimumOrder?: string
  source?: string
}
export type NextStepAction = { label: string; open: NextStepTarget }
export type ClarificationField = { key: string; label: string; kind: FieldKind }

/** Props each catalog component accepts. Nothing else reaches a component. */
export interface CatalogProps {
  /** A row of key figures; `label` names the group for assistive technology. */
  MetricRow: { label?: string; items: MetricItem[] }
  /** A comparison table; `title` is a visible heading, `label` the table's accessible name. */
  PlanComparison: {
    title?: string
    label?: string
    columns: string[]
    rows: string[][]
    highlightIndex?: number
  }
  /** Assumptions, sources and limits, folded by default; `label` is the fold's title. */
  EvidenceList: { label?: string; items: EvidenceItem[] }
  /** Remaining demand before and after, purchases kept and the gap this round fills (units). */
  DemandChange: { before: number; after: number; reason?: string; keep?: number; gap?: number }
  QuoteTable: { rows: QuoteRow[] }
  /** Entries into existing dialogs or views only. */
  NextStep: { actions: NextStepAction[] }
  /** Quick fields whose answer is sent as one plain sentence, like a typed reply. */
  ClarificationForm: { fields: ClarificationField[] }
  /** Markdown, rendered through the sanitizing MarkdownMessage. */
  Text: { markdown: string }
}
export type CatalogName = keyof CatalogProps
export type Block = { [K in CatalogName]: { component: K; props: CatalogProps[K] } }[CatalogName]
export type Surface = { version: 1; blocks: Block[] }

/**
 * Limits for surfaces that arrive from outside the frontend (validateSurface). Blocks never
 * contain blocks (nesting depth 1). Text is counted as UTF-8 bytes over every string kept.
 */
export const SURFACE_LIMITS = {
  blocks: 24,
  depth: 1,
  textBytes: 16 * 1024,
  /** A raw payload larger than this is not inspected at all. */
  rawChars: 256 * 1024,
} as const
