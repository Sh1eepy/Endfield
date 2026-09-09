import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, test, vi } from 'vitest'
import EntryCurtain from '../src/components/EntryCurtain'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  sessionStorage.clear()
  document.body.innerHTML = ''
})

test('entry curtain releases even when animation frames are paused', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.useFakeTimers()
  vi.stubGlobal('requestAnimationFrame', () => 1)
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)

  await act(async () => root.render(<EntryCurtain />))
  expect(host.querySelector('.entry-curtain')?.classList.contains('is-complete')).toBe(false)
  await act(async () => vi.advanceTimersByTime(2000))
  expect(host.querySelector('.entry-curtain')?.classList.contains('is-complete')).toBe(true)
  expect(sessionStorage.getItem('endfield-entry-seen')).toBe('1')
  await act(async () => root.unmount())
})
