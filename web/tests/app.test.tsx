import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from '../src/App'
import * as api from '../src/api'

vi.mock('../src/api', () => ({ fetchHealth: vi.fn(), fetchNames: vi.fn(), fetchAsk: vi.fn(), fetchSynthesis: vi.fn() }))
vi.mock('../src/components/EntryCurtain', () => ({ default: () => null }))
// 保留真实搜索框与答案组件，仅跳过动效和复杂详情展示。
vi.mock('../src/components/ResultPanel', async () => {
  const { default: AskResult } = await import('../src/components/AskResult')
  return { default: (p: any) => <div>
    <output>{p.state}|{p.mode}|{p.result?.query}|{p.errorMsg}</output>
    {p.result?.kind === 'ask' && <AskResult data={p.result.data} onPickName={p.onPickName} />}
    {p.state === 'empty' && <button id="empty-demo" onClick={() => p.onRunQuery('问答示例')}>示例</button>}
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
function deferred() {
  let resolve!: (value: any) => void
  let reject!: (error: Error) => void
  const promise = new Promise<any>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const state = () => document.querySelector('output')!.textContent
const value = () => document.querySelector('input')!.value

test('clicking current mode preserves query and result without refetch', async () => {
  await query('重息壤')
  await click('[data-mode="syn"]')
  expect(value()).toBe('重息壤')
  expect(state()).toBe('ready|syn|重息壤|')
  expect(api.fetchSynthesis).toHaveBeenCalledTimes(1)
})

test('late query response cannot overwrite newer result', async () => {
  const old = deferred()
  vi.mocked(api.fetchSynthesis).mockReturnValueOnce(old.promise)
  await query('旧查询')
  await query('新查询')
  await act(async () => old.resolve({ ok: true }))
  expect(state()).toBe('ready|syn|新查询|')
  expect(value()).toBe('新查询')
})

test('late error cannot overwrite newer result', async () => {
  const old = deferred()
  vi.mocked(api.fetchSynthesis).mockReturnValueOnce(old.promise)
  await query('旧查询')
  await query('新查询')
  await act(async () => old.reject(new Error('旧错误')))
  expect(state()).toBe('ready|syn|新查询|')
})

test('switching to empty mode invalidates pending request', async () => {
  const old = deferred()
  vi.mocked(api.fetchAsk).mockReturnValueOnce(old.promise)
  await click('[data-mode="ask"]')
  await query('问题')
  await click('[data-mode="syn"]')
  await act(async () => old.resolve({ ok: true, answer: '迟到答案' }))
  expect(state()).toBe('empty|syn||')
  expect(value()).toBe('')
})

test('clearing query invalidates pending response', async () => {
  const old = deferred()
  vi.mocked(api.fetchSynthesis).mockReturnValueOnce(old.promise)
  await query('旧查询')
  await query('')
  await act(async () => old.resolve({ ok: true }))
  expect(state()).toBe('empty|syn||')
})

test('source opens detail, preserves ask query and reuses cached answer', async () => {
  vi.mocked(api.fetchAsk).mockResolvedValue({ ok: true, answer: '冰淇淋[来源1]', sources: [
    { name: '莱万汀｜语音：帝江号闲聊5', category: '干员语音', score: 1 },
  ] })
  await query('重息壤')
  await click('[data-mode="ask"]')
  await query('莱万汀喜欢吃什么')
  await click('.ask-sources .ask-src-chip')
  expect(api.fetchSynthesis).toHaveBeenLastCalledWith('莱万汀')
  expect(state()).toBe('ready|syn|莱万汀|')
  await click('[data-mode="ask"]')
  expect(value()).toBe('莱万汀喜欢吃什么')
  expect(api.fetchAsk).toHaveBeenCalledTimes(1)
})

test('empty ask demo still submits an ask request', async () => {
  await click('[data-mode="ask"]')
  await click('#empty-demo')
  expect(api.fetchAsk).toHaveBeenCalledWith('问答示例')
  expect(api.fetchSynthesis).not.toHaveBeenCalled()
})

test('mode drafts are independent even when not submitted', async () => {
  await type('配方草稿')
  await click('[data-mode="ask"]')
  await type('问题草稿')
  await click('[data-mode="syn"]')
  expect(value()).toBe('配方草稿')
  await click('[data-mode="ask"]')
  expect(value()).toBe('问题草稿')
})
