export type LearningMode = 'off' | 'suggest' | 'assist'
export type SkillSpec = {
  title: string
  summary: string
  task_family: string
  inputs: string[]
  preconditions: string[]
  exclusions: string[]
  required_tools: string[]
  procedure: string[]
  outputs: string[]
  exceptions: string[]
}
export type QualityReport = {
  checks: Record<string, string>
  scores: Record<string, number | null>
  independent_cases: number
  suite_kinds: string[]
  evaluated_at: string
  expires_at: string
  dimension_reviews: Record<
    string,
    { score: number | null; reason: string; evidence_refs: string[] }
  >
}
export type SkillRevision = {
  revision: number
  status: string
  spec: SkillSpec
  evidence_ids: string[]
  evaluation_id: string | null
  quality: QualityReport | null
  quality_decision: { status: string; reasons: string[] } | null
  latest_check?: { id: string; evaluated_at: string; decision: { status: string } } | null
}
export type LearningAsset = {
  id: string
  version: number
  active_revision: number | null
  task_family: string
  kind: string
  revisions: SkillRevision[]
}
export type LearningView = {
  enabled: boolean
  policy: { version: number; mode: LearningMode; enabled_at: string | null }
  progress: {
    eligible_episodes: number
    first_checkpoint: number
    categories: Record<string, number>
    source_domain: string
    quality_calibrated: boolean
  }
  assets: LearningAsset[]
}
