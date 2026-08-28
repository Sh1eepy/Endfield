import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import AnswerMarkdown from '../src/components/AnswerMarkdown'
import SynTree from '../src/components/SynTree'
import treeCss from '../src/styles/tree.css?inline'

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

test('table cells retain inline formatting, alignment and clickable citations', async () => {
  const jump = vi.fn()
  await act(async () => root.render(<AnswerMarkdown answer={'| 食物 | 依据 |\n| :--- | ---: |\n| **冰淇淋** | 语音[来源1] |'} onJump={jump} />))
  expect(host.querySelectorAll('table')).toHaveLength(1)
  expect(host.querySelectorAll('th')).toHaveLength(2)
  expect(host.querySelector('td strong')?.textContent).toBe('冰淇淋')
  expect(host.querySelectorAll('td')[1].style.textAlign).toBe('right')
  await act(async () => host.querySelector<HTMLButtonElement>('td button')!.click())
  expect(jump).toHaveBeenCalledWith(1)
})

test('citations stay inside bold/list blocks instead of splitting them', async () => {
  await act(async () => root.render(<AnswerMarkdown answer={'- **事实[来源2]**\n- *解释*\n1. 第一条\n2. 第二条'} onJump={() => {}} />))
  expect(host.querySelectorAll('ul li')).toHaveLength(2)
  expect(host.querySelector('li strong .src-ref')).not.toBeNull()
  expect(host.querySelectorAll('ol li')).toHaveLength(2)
})

test('HTML is inert and citations inside code remain literal', async () => {
  await act(async () => root.render(<AnswerMarkdown answer={'<img src=x onerror=alert(1)>\n`[来源1]`\n```\n[来源2]\n```'} onJump={() => {}} />))
  expect(host.querySelector('img')).toBeNull()
  expect(host.querySelector('button')).toBeNull()
  expect(host.querySelector('pre code')?.textContent).toBe('[来源2]')
})

test('table parser keeps escaped pipes and code pipes in their cells', async () => {
  await act(async () => root.render(<AnswerMarkdown answer={'a | b\n--- | ---\nx\\|y | `a|b`\n'} onJump={() => {}} />))
  const row = host.querySelectorAll('td')
  expect(row).toHaveLength(2)
  expect(row[0].textContent).toBe('x|y')
  expect(row[1].textContent).toBe('a|b')
})

test('node label is pointer-enabled and supports click and keyboard', async () => {
  const pick = vi.fn()
  const style = document.createElement('style')
  style.textContent = treeCss
  host.append(style)
  const container = document.createElement('div')
  host.append(container)
  // 注入样式不放在 React 根内，避免渲染时被替换。
  document.head.append(style)
  try {
    await act(async () => root.render(<SynTree tree={{ name: '清水', item_id: 'water', depth: 0, leaf: true }} onPickName={pick} showTip={() => {}} hideTip={() => {}} />))
    const label = host.querySelector<SVGTextElement>('.node-card-label')!
    expect(getComputedStyle(label).pointerEvents).toBe('auto')
    await act(async () => label.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await act(async () => label.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
    expect(pick).toHaveBeenCalledTimes(2)
    expect(pick).toHaveBeenLastCalledWith('清水')
  } finally { style.remove() }
})
