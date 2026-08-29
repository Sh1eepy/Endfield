import type {
  AskResult, FeedbackResponse, HealthResponse, NamesResponse, SynthesisResponse,
} from './types'

async function apiError(res: Response): Promise<Error> {
  try {
    const body = await res.json()
    const detail = body?.detail || body?.error
    if (typeof detail === 'string' && detail) return new Error(detail)
  } catch { /* Proxies may return an HTML error page instead of JSON. */ }
  return new Error(`HTTP ${res.status}`)
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw await apiError(res)
  return res.json() as Promise<T>
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/health')
}

export function fetchNames(): Promise<NamesResponse> {
  return getJson<NamesResponse>('/api/names')
}

export function fetchSynthesis(item: string): Promise<SynthesisResponse> {
  return getJson<SynthesisResponse>(`/api/synthesis?item=${encodeURIComponent(item)}`)
}

export async function fetchAsk(query: string, topK = 5, genAnswer = true): Promise<AskResult> {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK, gen_answer: genAnswer, client_type: 'web' }),
  })
  if (!res.ok) throw await apiError(res)
  return res.json() as Promise<AskResult>
}

export async function submitFeedback(
  traceId: string, query: string, vote: 'useful' | 'not_useful', comment = '', observedAnswer = '',
): Promise<FeedbackResponse> {
  const res = await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trace_id: traceId, query, vote, comment,
      observed_answer: observedAnswer, client_type: 'web' }),
  })
  if (!res.ok) throw await apiError(res)
  return res.json() as Promise<FeedbackResponse>
}
