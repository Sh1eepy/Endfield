import {expect,test} from 'vitest'
import {TransitionCoordinator} from '../src/scene/transition'

test('page-scroll orbit follows slowly and reverses without an angle jump',()=>{
  const t=new TransitionCoordinator(0)
  t.orbit(.22)
  const first=t.step(1/60,1).scrollOrbit!
  expect(first).toBeGreaterThan(0);expect(first).toBeLessThan(.03)
  for(let i=0;i<120;i++)t.step(1/60,i+2)
  expect(t.scrollOrbit).toBeCloseTo(.22,4)
  t.orbit(0)
  expect(t.scrollOrbit).toBeGreaterThan(.21)
  for(let i=0;i<120;i++)t.step(1/60,i+122)
  expect(t.scrollOrbit).toBeCloseTo(0,4)
})

test('mode reversal preserves current position and velocity',()=>{
  const t=new TransitionCoordinator(0)
  t.select(1)
  for(let i=0;i<15;i++)t.step(1/60,i/60)
  const position=t.position,velocity=t.velocity
  t.select(0)
  expect(t.position).toBe(position);expect(t.velocity).toBe(velocity)
  for(let i=0;i<180;i++)t.step(1/60,i/60)
  expect(t.position).toBe(0);expect(t.velocity).toBe(0)
})
test('extraction opens and returns without resetting its pose',()=>{
  const t=new TransitionCoordinator(0)
  t.open(true)
  for(let i=0;i<30;i++)t.step(1/60,i/60)
  const mid=t.extraction
  expect(mid).toBeGreaterThan(.5);expect(mid).toBeLessThan(1)
  t.open(false)
  expect(t.extraction).toBe(mid)
  for(let i=0;i<240;i++)t.step(1/60,i/60)
  expect(t.extraction).toBe(0)
})
test('reduced motion and skip reach the final extraction immediately',()=>{
  const t=new TransitionCoordinator(0)
  t.select(1,true);t.open(true,true)
  const frame=t.step(1/60,1)
  expect(frame.position).toBe(1);expect(frame.extraction).toBe(1)
  expect(frame.energy).toBe(0)
})
test('large frame gaps stay bounded and browse coordinates remain finite',()=>{
  const t=new TransitionCoordinator(0)
  t.select(1);t.open(true);t.scroll(999)
  const frame=t.step(99,99)
  expect(frame.position).toBeLessThan(.2)
  expect(Number.isFinite(frame.browse)).toBe(true)
  expect(frame.browse).toBeLessThan(4)
})
