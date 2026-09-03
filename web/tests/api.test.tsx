import { afterEach, expect, test, vi } from 'vitest'
import {
  fetchAsk, fetchAskStream, fetchHealth, StreamUnavailableError, submitFeedback,
  type AskStreamEvent,
} from '../src/api'

afterEach(() => vi.unstubAllGlobals())

test.each([
  [429, { detail: '本站今日问答次数已用完' }, '本站今日问答次数已用完'],
  [401, { detail: '需要有效的访问令牌' }, '需要有效的访问令牌'],
  [429, { error: '请求过于频繁，请稍后重试' }, '请求过于频繁，请稍后重试'],
  [422, { detail: [{ msg: 'validation error' }] }, 'HTTP 422'],
])('ask displays a readable API error (%s)', async (status, body, expected) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status, json: async () => body }))
  await expect(fetchAsk('test')).rejects.toThrow(expected)
})

test('non-JSON proxy errors keep the HTTP status', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502,
    json: async () => { throw new SyntaxError('not JSON') } }))
  await expect(fetchHealth()).rejects.toThrow('HTTP 502')
})

test('feedback carries the trace and explicit reviewed content', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 201,
    json: async () => ({ ok: true, feedback_id: 'f', status: 'pending_review' }) })
  vi.stubGlobal('fetch', fetch)
  await submitFeedback('a'.repeat(32), 'query', 'not_useful', '', 'answer')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
    trace_id: 'a'.repeat(32), query: 'query', vote: 'not_useful', comment: '',
    observed_answer: 'answer', client_type: 'web',
  })
})

test('stream parser preserves UTF-8 split across chunks and ignores heartbeats', async () => {
  const wire = ': keep-alive\n\nevent: delta\ndata: {"text":"你好"}\n\n'
    + 'event: done\ndata: {"ok":true,"answer":"你好"}\n\n'
  const bytes = new TextEncoder().encode(wire)
  const firstMultibyte = bytes.findIndex((x) => x >= 0x80)
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes.slice(0, firstMultibyte + 1))
      controller.enqueue(bytes.slice(firstMultibyte + 1))
      controller.close()
    },
  })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, body }))
  const events: AskStreamEvent[] = []
  await expect(fetchAskStream('问题', (event) => events.push(event))).resolves.toBe(true)
  expect(events).toEqual([
    { event: 'delta', data: { text: '你好' } },
    { event: 'done', data: { ok: true, answer: '你好' } },
  ])
})

test('old backend stream route triggers the typed fallback error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))
  await expect(fetchAskStream('问题', () => {})).rejects.toBeInstanceOf(StreamUnavailableError)
})
