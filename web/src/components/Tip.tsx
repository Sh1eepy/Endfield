import type { ReactNode } from 'react'

export interface TipState {
  x: number
  y: number
  content: ReactNode
}

export default function Tip({ tip }: { tip: TipState | null }) {
  if (!tip) return null
  return (
    <div id="tip" className="visible" style={{ left: tip.x, top: tip.y }}>
      {tip.content}
    </div>
  )
}
