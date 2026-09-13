import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, test, vi } from 'vitest'
import Hero from '../src/components/Hero'

test('portrait rotation wraps, manual selection resets even the current portrait, and pin pauses', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers()
  const host = document.createElement('div'), root = createRoot(host)
  const portrait = () => host.querySelector('.hero-art img')?.getAttribute('alt')
  const click = async (selector: string) => act(async () => (host.querySelector(selector) as HTMLButtonElement).click())
  const advance = async (ms: number) => act(async () => vi.advanceTimersByTime(ms))
  try {
    await act(async () => root.render(<Hero onDemo={() => {}} />))
    expect(portrait()).toBe('佩丽卡官方立绘')
    for (const name of ['管理员', '莱万汀', '陈千语', '艾尔黛拉', '佩丽卡']) {
      await advance(8000)
      expect(portrait()).toBe(name + '官方立绘')
    }
    await advance(7000)
    await click('.hero-switcher button:first-child')
    await advance(1000)
    expect(portrait()).toBe('佩丽卡官方立绘')
    await advance(7000)
    expect(portrait()).toBe('管理员官方立绘')
    await click('.hero-switcher button:nth-child(4)')
    await advance(7999)
    expect(portrait()).toBe('陈千语官方立绘')
    await click('.hero-pin')
    expect(host.querySelector('.hero-pin')?.getAttribute('aria-pressed')).toBe('true')
    await advance(24000)
    expect(portrait()).toBe('陈千语官方立绘')
    await click('.hero-switcher button:nth-child(3)')
    await advance(16000)
    expect(portrait()).toBe('莱万汀官方立绘')
    await click('.hero-pin')
    await advance(7999)
    expect(portrait()).toBe('莱万汀官方立绘')
    await advance(1)
    expect(portrait()).toBe('陈千语官方立绘')
  } finally {
    await act(async () => root.unmount())
    expect(vi.getTimerCount()).toBe(0)
    vi.useRealTimers()
  }
})

test('hidden tabs suspend rotation and resume with a fresh interval', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers()
  const hidden = vi.spyOn(document, 'hidden', 'get')
  hidden.mockReturnValue(false)
  const host = document.createElement('div'), root = createRoot(host)
  try {
    await act(async () => root.render(<Hero onDemo={() => {}} />))
    await act(async () => vi.advanceTimersByTime(7000))
    hidden.mockReturnValue(true)
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    await act(async () => vi.advanceTimersByTime(20000))
    expect(host.querySelector('.hero-art img')?.getAttribute('alt')).toBe('佩丽卡官方立绘')
    hidden.mockReturnValue(false)
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    await act(async () => vi.advanceTimersByTime(8000))
    expect(host.querySelector('.hero-art img')?.getAttribute('alt')).toBe('管理员官方立绘')
  } finally { await act(async () => root.unmount()); hidden.mockRestore(); vi.useRealTimers() }
})
