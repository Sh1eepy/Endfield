import type { Mode } from '../App'

interface Props {
  onDemo: (query: string, mode: Mode) => void
}

export default function Hero({ onDemo }: Props) {
  return (
    <section className="hero">
      <img className="hero-logo" src="/assets/mascots/endfield-logo.png" alt="明日方舟：终末地" />
      <div>
        <div className="eyebrow">INDUSTRIAL RECIPE DATABASE / 01</div>
        <h1>从上到下<span>看清制造</span></h1>
        <p className="hero-copy">
          <b>每个物品和设备都以真实封面呈现。</b> 345 条配方被展开为纵向生产流程，
          保持清晰尺寸，也允许随时折叠、缩放与跳转。
        </p>
        <div className="hero-actions">
          <button className="action-btn" onClick={() => onDemo('重息壤', 'syn')}>查看示例配方</button>
          <button className="action-btn secondary" onClick={() => onDemo('佩丽卡怎么玩', 'ask')}>试试知识问答</button>
        </div>
      </div>
      <div className="hero-stats">
        <div className="stat"><b>345</b><span>VERIFIED<br />RECIPES</span></div>
        <div className="stat"><b>1,958</b><span>WIKI<br />ENTRIES</span></div>
        <div className="stat"><b>100%</b><span>RECALL<br />AT 5</span></div>
      </div>
    </section>
  )
}
