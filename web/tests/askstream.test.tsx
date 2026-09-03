import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from '../src/App'
import * as api from '../src/api'
import type { AskStreamEvent } from '../src/api'

vi.mock('../src/api', async () => {
  const actual = await vi.importActual<typeof api>('../src/api')
  return {
    ...actual,
    fetchHealth: vi.fn(), fetchNames: vi.fn(), fetchAsk: vi.fn(),
    fetchSynthesis: vi.fn(), fetchAskStream: vi.fn(),
  }
})
vi.mock('../src/components/EntryCurtain', () => ({ default: () => null }))
vi.mock('../src/components/ResultPanel', async () => {
  const { default: AskResult } = await import('../src/components/AskResult')
  return { default: (p: any) => <div>
    <output>{p.state}|{p.mode}|{p.result?.query}|{p.errorMsg}</output>
    {p.result?.kind === 'ask' && <AskResult data={p.result.data} onPickName={p.onPickName} />}
  </div> }
})

let host: HTMLDivElement
let root: Root
beforeEach(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  localStorage.clear()
  vi.resetAllMocks()
  vi.mocked(api.fetchHealth).mockResolvedValue({ status: 'ok', service: 'test' })
  vi.mocked(api.fetchNames).mockResolvedValue({ names: [], count: 0 })
  vi.mocked(api.fetchSynthesis).mockResolvedValue({ ok: true })
  vi.mocked(api.fetchAsk).mockResolvedValue({ ok: true, answer: '回答' })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  await act(async () => root.render(<App />))
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

async function click(selector: string) {
  await act(async () => (host.querySelector(selector) as HTMLElement).click())
}
async function type(value: string) {
  const input = host.querySelector('input')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function query(value: string) {
  await type(value)
  await act(async () => host.querySelector('input')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
}
const state = () => document.querySelector('output')!.textContent
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

test('streaming ask renders phase then incremental text then final answer', async () => {
  const events: AskStreamEvent[] = [
    { event: 'phase', data: { stage: 'route', text: '正在检索知识库…' } },
    { event: 'meta', data: { ok: true, route_used: 'rag', intent: '知识',
      sources: [{ name: '重息壤', category: '物品', score: 0.9 }] } },
    { event: 'delta', data: { text: '你' } },
    { event: 'delta', data: { text: '好' } },
    { event: 'done', data: { ok: true, route_used: 'rag', intent: '知识',
      answer: '你好', rejected: false,
      sources: [{ name: '重息壤', category: '物品', score: 0.9 }],
      trace_id: 'a'.repeat(32), feedback_snapshot: '' } },
  ]
  vi.mocked(api.fetchAskStream).mockImplementation(async (_q, onEvent) => {
    for (const ev of events) onEvent(ev)
    return true
  })

  await click('[data-mode="ask"]')
  await query('重息壤是什么')
  await act(async () => { await sleep(150) }) // 让 80ms 节流渲染落地
  expect(api.fetchAskStream).toHaveBeenCalledTimes(1)
  expect(state()).toBe('ready|ask|重息壤是什么|')
  const text = host.textContent || ''
  expect(text).toContain('你好')
  expect(text).not.toContain('正在检索知识库') // done 后阶段文案不残留
  // done 已回答，反馈区出现且不处于流式态
  expect(host.querySelector('.ask-feedback')).toBeTruthy()
})

test('stream error after partial text keeps partial content', async () => {
  vi.mocked(api.fetchAskStream).mockImplementation(async (_q, onEvent) => {
    onEvent({ event: 'delta', data: { text: '半截回答' } })
    onEvent({ event: 'error', data: { message: '生成中断测试' } })
    return false
  })
  await click('[data-mode="ask"]')
  await query('问题')
  await act(async () => { await sleep(150) })
  expect(host.textContent).toContain('半截回答')
  expect(host.textContent).toContain('生成中断测试')
})

test('stream close without done clears streaming state and keeps partial content', async () => {
  vi.mocked(api.fetchAskStream).mockImplementation(async (_q, onEvent) => {
    onEvent({ event: 'delta', data: { text: '半截回答' } })
    return false
  })
  await click('[data-mode="ask"]')
  await query('问题')
  await act(async () => { await sleep(150) })
  expect(host.textContent).toContain('半截回答')
  expect(host.textContent).toContain('回答生成中断，已保留已生成的内容')
  expect(host.textContent).not.toContain('▍')
})

test('terminal error cancels a pending throttled phase render', async () => {
  vi.mocked(api.fetchAskStream).mockImplementation(async (_q, onEvent) => {
    onEvent({ event: 'phase', data: { stage: 'route', text: '正在检索知识库…' } })
    onEvent({ event: 'done', data: { ok: false, error: '查询失败' } })
    return true
  })
  await click('[data-mode="ask"]')
  await query('问题')
  await act(async () => { await sleep(150) })
  expect(state()).toBe('error|ask||查询失败')
  expect(host.textContent).not.toContain('正在检索知识库')
})
