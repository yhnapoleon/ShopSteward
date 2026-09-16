import { ref } from 'vue'
import english from './en.json' with { type: 'json' }

export type Locale = 'zh-CN' | 'en'
// This app is client rendered (ssr: false). One reactive preference is shared by all views.
export const locale = ref<Locale>('zh-CN')
export const preferenceError = ref('')
export const localeKey = 'shopsteward.locale.v1'
export const intlLocale = () => (locale.value === 'en' ? 'en-SG' : 'zh-CN')
const catalog: Record<string, string> = english
const normalize = (text: string) => text.replace(/\s+/g, ' ').trim()
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
// Legacy generated system messages use the same source templates as the UI.
// Match complete messages only; never replace substrings in documents or user input.
const patterns = Object.entries(catalog)
  .filter(([key]) => /\{\d+\}/.test(key))
  .map(([key, value]) => {
    const indices: number[] = []
    const chunks = key.split(/(\{\d+\})/g)
    const pattern = chunks
      .map((chunk) => {
        if (/^\{\d+\}$/.test(chunk)) {
          indices.push(Number(chunk.slice(1, -1)))
          return '(.+?)'
        }
        return escape(chunk).replace(/\s+/g, '\\s+')
      })
      .join('')
    return { key, regex: new RegExp('^' + pattern + '$'), value, indices }
  })
export function t<T>(source: T, values?: Array<string | number>): T {
  if (typeof source !== 'string') return source
  const key = normalize(source)
  let output: string = source
  if (locale.value === 'en') {
    if (Object.prototype.hasOwnProperty.call(catalog, key)) output = catalog[key]!
    else if (/[\u3400-\u9fff]/.test(key)) {
      for (const entry of patterns) {
        const match = entry.regex.exec(source.trim())
        if (!match) continue
        const parameters: string[] = []
        entry.indices.forEach((index, i) => {
          parameters[index] =
            entry.key === '第{0}条报价：{1}' && index === 1
              ? String(t(match[i + 1]!))
              : match[i + 1]!
        })
        output = entry.value.replace(/\{(\d+)\}/g, (_, index) => parameters[Number(index)] ?? '')
        break
      }
    }
  }
  if (values)
    output = output.replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)] ?? ''))
  return output as T
}
export function setLocale(next: Locale) {
  if (!['zh-CN', 'en'].includes(next)) return
  preferenceError.value = ''
  // Apply immediately, even when browser persistence is unavailable.
  locale.value = next
  try {
    localStorage.setItem(localeKey, next)
  } catch {
    preferenceError.value = '语言已切换，但浏览器无法保存偏好；刷新后可能恢复中文。'
  }
}
export function readLocale() {
  try {
    const saved = localStorage.getItem(localeKey)
    locale.value = saved === 'en' ? 'en' : 'zh-CN'
  } catch {
    locale.value = 'zh-CN'
  }
}

/** Separate English words around live values without changing Chinese spacing. */
export function joinText(parts: unknown[], chineseSeparator = '') {
  return parts
    .map((value) => String(value ?? ''))
    .join(locale.value === 'en' ? ' ' : chineseSeparator)
}
