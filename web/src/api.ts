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

// ---------- 流式问答（/api/ask/stream，SSE）----------

export type AskStreamEventName = 'phase' | 'meta' | 'delta' | 'done' | 'error' | 'message'

export interface AskStreamEvent {
  event: AskStreamEventName
  data: Record<string, unknown>
}

/** 后端未提供 /api/ask/stream（旧部署）时抛出，调用方可回退到整包 /api/ask。 */
export class StreamUnavailableError extends Error {
  constructor() {
    super('stream-unavailable')
    this.name = 'StreamUnavailableError'
  }
}

/** 逐块解析 SSE 文本流；每条事件以空行分隔，event: 行 + data: 行。 */
async function consumeSse(body: ReadableStream<Uint8Array>, onEvent: (ev: AskStreamEvent) => void): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let sep: number
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        let event: string = 'message'
        let dataStr = ''
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) dataStr += line.slice(5).trim()
          // 心跳注释行（: keep-alive）与空行直接忽略
        }
        if (!dataStr) continue
        try {
          onEvent({ event: event as AskStreamEventName, data: JSON.parse(dataStr) })
        } catch { /* 忽略损坏帧，不中断整条流 */ }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

/**
 * 流式调用 /api/ask/stream。
 * 事件顺序：phase → meta（sources 先亮）→ delta×N → done（完整结果）。
 * 返回 true 表示收到了 done 事件；中途异常抛出（AbortError / 网络错误）。
 */
export async function fetchAskStream(
  query: string,
  onEvent: (ev: AskStreamEvent) => void,
  signal?: AbortSignal,
): Promise<boolean> {
  const res = await fetch('/api/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: 5, gen_answer: true, client_type: 'web' }),
    signal,
  })
  if (res.status === 404 || res.status === 405) throw new StreamUnavailableError()
  if (!res.ok) throw await apiError(res)
  let gotDone = false
  await consumeSse(res.body!, (ev) => {
    if (ev.event === 'done') gotDone = true
    onEvent(ev)
  })
  return gotDone
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
