// 通用工具：媒体代理、历史记录、字符串工具。

export function mediaSrc(url: string | undefined | null): string {
  const u = String(url || '')
  if (u.startsWith('https://bbs.hycdn.cn/image/') || u.startsWith('https://bbs.hycdn.cn/audio/')) {
    return `/api/media?url=${encodeURIComponent(u)}`
  }
  return u
}

const HISTORY_KEY = 'endfield-search-history-v1'
const HISTORY_LIMIT = 8

export interface HistoryEntry { q: string; mode: 'syn' | 'ask' }

export function getHistory(): HistoryEntry[] {
  try {
    const value = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
    return Array.isArray(value)
      ? value.filter((x: HistoryEntry) => x && x.q).slice(0, HISTORY_LIMIT)
      : []
  } catch {
    return []
  }
}

export function recordHistory(q: string, mode: 'syn' | 'ask'): HistoryEntry[] {
  const clean = String(q || '').trim()
  if (!clean) return getHistory()
  const next = [
    { q: clean, mode },
    ...getHistory().filter((x) => x.q !== clean || x.mode !== mode),
  ].slice(0, HISTORY_LIMIT)
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
  } catch {
    /* localStorage 不可用（隐私模式等）时静默 */
  }
  return next
}

export function clearHistory(): void {
  try {
    localStorage.removeItem(HISTORY_KEY)
  } catch {
    /* ignore */
  }
}

export function escapeHtml(s: unknown): string {
  return String(s ?? '').replace(/[&<>"]/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string
  ))
}
