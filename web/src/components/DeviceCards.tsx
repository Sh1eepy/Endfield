import type { SynTree as SynTreeApi } from '../types'

interface Props {
  tree: SynTreeApi
}

/** 设备配方卡（/api/synthesis 设备分支） */
export default function DeviceCards({ tree }: Props) {
  const recipes = tree.recipes || []
  return (
    <div>
      <div style={{ color: 'var(--sub)', margin: '8px 0 12px', fontSize: 14 }}>
        设备 <b style={{ color: 'var(--accent3)' }}>{tree.name}</b> 共有 {recipes.length} 个配方：
      </div>
      {recipes.map((r, i) => (
        <div key={i} className="msg bot">
          <b style={{ color: 'var(--klein)' }}>{r.machine}</b> · 耗时 {r.duration}s<br />
          <span style={{ color: 'var(--sub)' }}>原料：</span>
          {(r.inputs || []).map((x) => `${x.name}×${x.count}`).join('、') || '—'}<br />
          <span style={{ color: 'var(--sub)' }}>产物：</span>
          {(r.outputs || []).map((x) => `${x.name}×${x.count}`).join('、')}
        </div>
      ))}
    </div>
  )
}
