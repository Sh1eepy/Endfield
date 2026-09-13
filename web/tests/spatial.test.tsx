import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { test, expect, vi } from 'vitest'
import { helixPoint, ARCHIVE_FACE } from '../src/scene/archiveGeometry'
import RetrievalStatus from '../src/components/RetrievalStatus'

test('paired archive positions stay opposite through the biological wave',()=>{
  for(let y=-20;y<=20;y+=.5)for(const time of [0,3,19]) {
    const a=helixPoint(y,0,time),b=helixPoint(y,1,time)
    expect(a[0]+b[0]).toBeCloseTo(0,10)
    expect(a[2]+b[2]).toBeCloseTo(0,10)
    expect(Math.hypot(a[0],a[2])).toBeGreaterThanOrEqual(4.78)
    expect(Math.hypot(a[0],a[2])).toBeLessThanOrEqual(5.42)
    expect(a[1]).toBeCloseTo(b[1],10)
    expect(Math.abs(a[1]-y)).toBeLessThanOrEqual(.22)
  }
  expect(ARCHIVE_FACE.depth/ARCHIVE_FACE.width).toBeLessThan(.15)
})

test('retrieval stays indeterminate through phase changes and clears its timer',async()=>{
  Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
  vi.useFakeTimers()
  const host=document.createElement('div'),root=createRoot(host)
  try {
    await act(async()=>root.render(<RetrievalStatus active identity="one" />))
    expect(host.textContent).toContain('等待服务响应')
    expect(host.querySelector('[role="progressbar"]')?.hasAttribute('aria-valuenow')).toBe(false)
    await act(async()=>root.render(<RetrievalStatus active identity="one" phase="正在检索证据" />))
    expect(host.textContent).toContain('正在检索证据')
    expect(vi.getTimerCount()).toBe(1)
    await act(async()=>root.render(<RetrievalStatus active={false} identity="one" />))
    expect(host.textContent).toBe('')
    expect(vi.getTimerCount()).toBe(0)
  } finally {await act(async()=>root.unmount());vi.useRealTimers()}
})
