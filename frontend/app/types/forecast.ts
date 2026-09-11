export type ForecastMode = 'observed' | 'historical_demo'
export interface ForecastHistory {
  date: string
  sold_quantity: number
  complete: boolean
}
export interface ForecastModel {
  model_version: string
  feature_profile: string
  minimum_history_days: number
  recommended_history_days: number
  supported_series: {
    series_id: string
    item_id: string
    store_id: string
    dept_id: string
    cat_id: string
    state_id: string
  }[]
  weights: Record<string, number>
  evaluation: Record<string, unknown>
  limitations: string[]
}
export interface ForecastEvidence {
  forecast_id: string
  model_version: string
  series_id: string
  store_id: string
  sku_id: string
  observation_end_date: string
  horizon_start: string
  horizon_end: string
  daily_predictions: { date: string; quantity: number }[]
  total_quantity_raw: number
  predicted_quantity: number
  generated_at: string
  valid_until: string
  assumptions: string[]
  evaluation: Record<string, unknown>
}
export interface ForecastCurrent {
  status: 'READY' | 'STALE' | 'UNAVAILABLE'
  reason: string | null
  store_id: string
  sku_id: string
  mode: ForecastMode | null
  usable_for_planning: boolean
  activate_for_planning: boolean
  forecast: ForecastEvidence | null
  history: ForecastHistory[]
  model: ForecastModel | null
}
export interface ForecastReference {
  id: string
  storeId: string
  skuId: string
  nonce: number
}
