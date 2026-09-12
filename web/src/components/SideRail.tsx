import type { Mode } from '../App'

export default function SideRail({ mode }: { mode: Mode }) {
  return (
    <aside className="side-rail">
      <div className="rail-title">ARCHIVE INDEX</div>
      <div className="rail-item">
        <b>OPERATION</b>
        <span>{mode === 'syn' ? '输入名称后展开合成路径，圆点可折叠分支。' : '提出问题，检索相关档案。回答中的来源可展开核对。'}</span>
      </div>
      <div className="rail-item">
        <b>{mode === 'syn' ? 'NODE LEGEND' : 'READING GUIDE'}</b>
        {mode === 'syn' ? (
        <div className="rail-legend">
          <i className="legend-dot" /><span>可制造物品</span>
          <i className="legend-dot recipe" /><span>生产设备</span>
          <i className="legend-dot base" /><span>基础资源</span>
        </div>
        ) : <span>检索证据 → 阅读回答 → 核对来源<br />证据不足时，不作确定推断。</span>}
      </div>
      <div className="rail-item">
        <b>DATA SOURCE</b>
        <span>终末地官方 WIKI<br />本地离线索引</span>
      </div>
    </aside>
  )
}
