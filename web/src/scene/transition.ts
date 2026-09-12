/** Critical damping adapted from RhineLabUI motion.ts (MIT; docs/THIRD_PARTY_NOTICES.md). */
export function damp(value: number, velocity: number, target: number, rate: number, dt: number) {
  const offset = value - target
  const impulse = velocity + rate * offset
  const decay = Math.exp(-rate * dt)
  return { value: target + (offset + impulse * dt) * decay, velocity: (velocity - rate * impulse * dt) * decay }
}
export interface TransitionFrame { position: number; velocity: number; energy: number; pointerX: number; pointerY: number; time: number; extraction: number; browse: number; scrollOrbit?: number }
/** Camera, glass panels, background masks and typography consume one clock. */
export class TransitionCoordinator {
  position: number
  velocity = 0
  target: number
  pointerX = 0
  pointerY = 0
  private pointerTarget = [0, 0]
  extraction = 0
  private extractVelocity = 0
  private extractTarget = 0
  browse = 0
  private browseTarget = 0
  scrollOrbit = 0
  private orbitTarget = 0
  orbit(position:number) { if(Number.isFinite(position))this.orbitTarget=position }
  constructor(initial: number) { this.position = this.target = initial }
  select(target: number, immediate = false) {
    this.target = target
    if (immediate) { this.position = target; this.velocity = 0 }
  }
  point(x: number, y: number) { this.pointerTarget = [Math.max(-1, Math.min(1, x)), Math.max(-1, Math.min(1, y))] }
  open(active: boolean, immediate = false) {
    this.extractTarget = active ? 1 : 0
    if (immediate) { this.extraction = this.extractTarget; this.extractVelocity = 0 }
  }
  scroll(delta: number) { this.browseTarget += Math.max(-4, Math.min(4,delta)) }
  step(delta: number, time: number): TransitionFrame {
    const dt = Math.max(0, Math.min(.05, delta))
    const next = damp(this.position, this.velocity, this.target, 8, dt)
    this.position = next.value
    this.velocity = next.velocity
    if (Math.abs(this.position - this.target) < .0001 && Math.abs(this.velocity) < .001) { this.position = this.target; this.velocity = 0 }
    const blend = 1 - Math.exp(-dt * 5)
    this.scrollOrbit += (this.orbitTarget-this.scrollOrbit)*blend
    this.pointerX += (this.pointerTarget[0] - this.pointerX) * blend
    this.pointerY += (this.pointerTarget[1] - this.pointerY) * blend
    const extraction = damp(this.extraction,this.extractVelocity,this.extractTarget,6.5,dt)
    this.extraction=extraction.value; this.extractVelocity=extraction.velocity
    if (Math.abs(this.extraction-this.extractTarget)<.0001 && Math.abs(this.extractVelocity)<.001) { this.extraction=this.extractTarget; this.extractVelocity=0 }
    this.browse += (this.browseTarget-this.browse)*(1-Math.exp(-dt*7))
    return { position: this.position, velocity: this.velocity, energy: Math.min(1, Math.abs(this.velocity) * .35), pointerX: this.pointerX, pointerY: this.pointerY, time, extraction: this.extraction, browse: this.browse, scrollOrbit:this.scrollOrbit }
  }
}
