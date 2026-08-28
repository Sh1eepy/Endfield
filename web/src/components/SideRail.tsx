export default function SideRail() {
  return (
    <aside className="side-rail">
      <div className="rail-title">ARCHIVE INDEX</div>
      <div className="rail-item">
        <b>OPERATION</b>
        <span>输入名称后展开完整生产链，圆点可折叠分支。</span>
      </div>
      <div className="rail-item">
        <b>NODE LEGEND</b>
        <div className="rail-legend">
          <i className="legend-dot" /><span>可制造物品</span>
          <i className="legend-dot recipe" /><span>生产设备</span>
          <i className="legend-dot base" /><span>基础资源</span>
        </div>
      </div>
      <div className="rail-item">
        <b>DATA SOURCE</b>
        <span>终末地官方 WIKI<br />本地离线索引</span>
      </div>
      <img className="frame-mascot mascot-rail" src="/assets/mascots/mascot-08.png" alt="" />
    </aside>
  )
}
