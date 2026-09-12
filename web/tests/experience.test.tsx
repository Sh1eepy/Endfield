import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, test, vi } from 'vitest'
import ArchiveExperience from '../src/components/ArchiveExperience'

test('reduced motion keeps the official-art fallback and never mounts a canvas', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  const host = document.createElement('div')
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ArchiveExperience mode="syn" />))
    expect(host.querySelector('canvas')).toBeNull()
    expect(host.querySelector('.experience-art')).not.toBeNull()
    await act(async () => root.render(<ArchiveExperience mode="ask" />))
    expect(host.textContent).toContain('循着线索')
    expect(host.textContent).not.toContain('循着线索。')
    expect(host.textContent).not.toContain('解析构成。')
    expect(host.querySelector('canvas')).toBeNull()
  } finally {
    await act(async () => root.unmount())
    vi.unstubAllGlobals()
  }
})

test('phase-only results do not extract; content opens once and dismissal survives streaming updates', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  const host=document.createElement('div'),root=createRoot(host)
  const render=async(hasContent:boolean,identity='问题一')=>act(async()=>root.render(<ArchiveExperience mode="ask" resultState="ready" hasContent={hasContent} resultIdentity={identity}><p>真实回答</p></ArchiveExperience>))
  try {
    await render(false)
    expect(host.querySelector('.archive-experience')?.getAttribute('data-detail')).toBe('false')
    await render(true)
    expect(host.querySelector('.archive-experience')?.getAttribute('data-detail')).toBe('true')
    expect(host.querySelector('.archive-status')?.textContent).not.toContain('档案内容已就绪')
    await act(async()=>(host.querySelector('.archive-detail-bar button') as HTMLButtonElement).click())
    await render(true)
    expect(host.querySelector('.archive-experience')?.getAttribute('data-detail')).toBe('false')
    expect(host.textContent).toContain('真实回答')
    await render(true,'问题二')
    expect(host.querySelector('.archive-experience')?.getAttribute('data-detail')).toBe('true')
  } finally {await act(async()=>root.unmount());vi.unstubAllGlobals()}
})

test('errors remain readable and stopping is available before the first answer token', async () => {
  Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
  vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()}))
  const host=document.createElement('div'),root=createRoot(host),stop=vi.fn()
  try {
    await act(async()=>root.render(<ArchiveExperience mode="ask" resultState="loading" streaming onStop={stop} />))
    await act(async()=>(host.querySelector('.archive-status button') as HTMLButtonElement).click())
    expect(stop).toHaveBeenCalledOnce()
    await act(async()=>root.render(<ArchiveExperience mode="ask" resultState="error"><p>连接失败</p></ArchiveExperience>))
    expect(host.querySelector('.archive-detail')?.getAttribute('aria-hidden')).toBe('false')
    expect(host.querySelector('.archive-experience')?.getAttribute('data-detail')).toBe('true')
  } finally {await act(async()=>root.unmount());vi.unstubAllGlobals()}
})
