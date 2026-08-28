interface Props {
  connected: boolean
}

export default function TopBar({ connected }: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark"><img src="/assets/mascots/endfield-logo.png" alt="终末地" /></div>
        <div>
          <div className="brand-cn">终末地工业 · 合成档案</div>
          <div className="brand-en">ENDFIELD SYNTHESIS ARCHIVE</div>
        </div>
      </div>
      <div className="top-meta">
        <span className="top-code">TALOS-II / DATA TERMINAL 07</span>
        <div className="status">
          <span className={`dot${connected ? ' on' : ''}`} id="api-dot" />
          <span id="api-text">{connected ? '后端已连接' : '后端未连接'}</span>
        </div>
      </div>
    </header>
  )
}
