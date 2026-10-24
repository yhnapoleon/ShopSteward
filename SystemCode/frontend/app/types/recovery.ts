import type { Schema } from './models'
export type RecoveryDay = Schema<'DailyBalance'>
export type RecoveryCandidate = Schema<'RecoveryCandidate'>
export type RecoveryProposal = Schema<'RecoveryProposal'>
export type RecoveryCase = Schema<'CaseDetail'>

// The sourcing run is stored as written by the reviewers and the gate, so it is typed here.
export type OfferCard = {
  supplier_id: string
  status: 'offer' | 'no_offer'
  reason: string | null
  offer: {
    unit_price_minor: number
    minimum_order_quantity: number
    pack_size: number
    lead_time_days: number
    valid_from: string
    valid_until: string
    offer_version: string
  } | null
  history: { deliveries: number; late: number }
  citations: { field: string; doc_id: string; quote: string }[]
}
export type SupplierReview = {
  supplier_id: string
  name?: string
  status: 'accepted' | 'unreviewed'
  card: OfferCard | null
  attempts: {
    attempt: number
    model: string
    opened: string[]
    problems: string[]
    reasons: string[]
  }[]
}
export type Sourcing = {
  status: 'running' | 'complete' | 'partial' | 'failed'
  run_id: string
  revision: number
  request: {
    sku_id: string
    district: string
    as_of: string
    shortfall_qty: number
    short_from: string | null
  }
  suppliers: { supplier_id: string; name: string; documents: { doc_id: string; kind: string }[] }[]
  reviews: SupplierReview[]
  unreviewed?: string[]
  registered?: string[]
  left_out?: string[]
  review_bundle?: { revision: string; content_hash: string }
  explain_bundle?: string
  missing?: string[]
}
