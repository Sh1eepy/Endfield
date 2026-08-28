import type {
  AskResult, HealthResponse, NamesResponse, SynthesisResponse,
} from './types'

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
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
    body: JSON.stringify({ query, top_k: topK, gen_answer: genAnswer }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<AskResult>
}
