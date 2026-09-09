interface Props {
  connected: boolean
}

export default function TopBar({ connected }: Props) {
  return (
    <header className="topbar">
      <a className="brand" href="#page-top" aria-label="返回页面顶部">
        <div className="brand-mark"><img src="/assets/mascots/endfield-logo.png" alt="终末地" /></div>
        <div>
          <div className="brand-cn">终末地工业 · 合成档案</div>
          <div className="brand-en">ENDFIELD SYNTHESIS ARCHIVE</div>
        </div>
      </a>
      <nav className="top-nav" aria-label="页面导航">
        <a href="#page-top" aria-label="前往首页"><span className="nav-index">00</span><span className="nav-glyph" aria-hidden="true">✳</span><span className="nav-label">HOME</span></a>
        <a href="#search-command" aria-label="前往查询">
          <span className="nav-index">01</span><span className="nav-glyph" aria-hidden="true">⌕</span>
          <span className="nav-label">QUERY</span>
        </a>
        <a href="#workspace" aria-label="前往结果区">
          <span className="nav-index">02</span><span className="nav-glyph" aria-hidden="true">⌘</span>
          <span className="nav-label">RESULT</span>
        </a>
      </nav>
      <div className="top-meta">
        <span className="top-code">TALOS-II / DATA TERMINAL 07</span>
        <div className="status" title={connected ? '后端已连接' : '后端未连接'}>
          <span className={`dot${connected ? ' on' : ''}`} id="api-dot" />
          <span id="api-text">{connected ? '后端已连接' : '后端未连接'}</span>
        </div>
      </div>
    </header>
  )
}
