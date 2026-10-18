import { sanitizeBlock, type Budget } from './catalog'
import { SURFACE_LIMITS, type Block, type Surface } from './types'

/**
 * A surface that arrives from outside the frontend (for example a future `surface` field on a
 * work result), reduced to what the catalog allows. Unknown components become Text when they
 * carry readable words; invalid blocks are dropped. The whole surface is refused (null) when it
 * is not version 1, has no blocks or more than 24, is too large, or exceeds 16 KB of text; the
 * caller then derives a surface from the structured result instead.
 */
export function validateSurface(raw: unknown): Surface | null {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null
  const value = raw as { version?: unknown; blocks?: unknown }
  if (value.version !== 1 || !Array.isArray(value.blocks)) return null
  if (!value.blocks.length || value.blocks.length > SURFACE_LIMITS.blocks) return null
  try {
    if (JSON.stringify(raw).length > SURFACE_LIMITS.rawChars) return null
    const budget: Budget = { bytes: SURFACE_LIMITS.textBytes }
    const blocks: Block[] = []
    for (const candidate of value.blocks) {
      const block = sanitizeBlock(candidate, budget)
      if (block) blocks.push(block)
    }
    return blocks.length ? { version: 1, blocks } : null
  } catch {
    // Over the text allowance, or not serializable: nothing of it is shown.
    return null
  }
}
