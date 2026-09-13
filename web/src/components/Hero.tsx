import { useEffect, useState } from 'react'
import type { Mode } from '../App'

interface Props { onDemo: (query: string, mode: Mode) => void }
const OPERATORS = [
  { name: '佩丽卡', en: 'PERLICA', image: 'perlica-portrait.png', role: '终末地工业 · 监督' },
  { name: '管理员', en: 'ENDMINISTRATOR', image: 'endministrator-portrait.png', role: '终末地工业 · 管理员' },
  { name: '莱万汀', en: 'LAEVATAIN', image: 'laevatain-portrait.png', role: '干员档案 · 莱万汀' },
  { name: '陈千语', en: 'CHEN QIANYU', image: 'chen-portrait.png', role: '干员档案 · 陈千语' },
  { name: '艾尔黛拉', en: 'ARDELIA', image: 'ardelia-portrait.png', role: '干员档案 · 艾尔黛拉' },
]
export default function Hero({ onDemo }: Props) {
  const [selected, setSelected] = useState(0)
  const [pinned, setPinned] = useState(false)
  const [restart, setRestart] = useState(0)
  useEffect(() => {
    if (pinned) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const schedule = () => {
      clearTimeout(timer)
      if (!document.hidden) timer = setTimeout(() => setSelected(value => (value + 1) % OPERATORS.length), 8000)
    }
    schedule()
    document.addEventListener('visibilitychange', schedule)
    return () => { clearTimeout(timer); document.removeEventListener('visibilitychange', schedule) }
  }, [selected, pinned, restart])
  const selectOperator = (index: number) => { setSelected(index); setRestart(value => value + 1) }
  const operator = OPERATORS[selected]
  return (
    <section className="hero" aria-label="终末地档案首页">
      <div className="hero-registration" aria-hidden="true"><span>ENDFIELD INDUSTRIES</span><span>ARCHIVE / TALOS-II</span><i /></div>
      <div className="hero-wordmark" aria-hidden="true">ENDFIELD</div>
      <div className="hero-yellow-field" aria-hidden="true" />
      <div className="hero-art" key={operator.en}>
        <img src={'/assets/official/' + operator.image} alt={operator.name + '官方立绘'} loading="eager" />
      </div>
      <div className="hero-copy-block">
        <div className="eyebrow"><span>ARKNIGHTS: ENDFIELD</span><i className="color-register" aria-hidden="true" /></div>
        <h1><span className="hero-line"><i>开拓边界</i></span><span className="hero-line"><i>连接万象<span className="title-stop" aria-hidden="true" /></i></span></h1>
        <div className="hero-subtitle">终末地 · 合成与知识档案</div>
        <p className="hero-copy">从一件原料，到完整生产链。<br />让每一次探索，都有迹可循。</p>
        <a className="hero-enter" href="#search-command"><span>进入档案</span><span aria-hidden="true">↗</span></a>
        <div className="hero-character-label"><b>{operator.en}</b><span>{operator.role}</span></div>
      </div>
      <div className="hero-bottom">
        <div className="hero-switcher" aria-label="切换首页角色">
          {OPERATORS.map((item, index) => <button key={item.en} aria-pressed={selected === index} onClick={() => selectOperator(index)}><span>0{index + 1}</span>{item.name}<i aria-hidden="true" /></button>)}
          <button type="button" className="hero-pin" aria-label="固定当前立绘" aria-pressed={pinned} title={pinned ? '取消固定，恢复每 8 秒轮播' : '固定当前立绘，暂停轮播'} onClick={() => setPinned(value => !value)}><span aria-hidden="true">{pinned ? '■' : 'Ⅱ'}</span>{pinned ? '已固定' : '固定立绘'}</button>
        </div>
        <div className="hero-dock">
          <div className="dock-index"><span>LOCAL ARCHIVE</span><strong>345<span> 配方</span></strong><small>1,958 条知识条目</small></div>
          <button className="dock-action" onClick={() => onDemo('重息壤', 'syn')}><span className="dock-symbol" aria-hidden="true">⌘</span><span><small>SYNTHESIS</small><b>查看示例配方</b></span><i aria-hidden="true">↗</i></button>
          <button className="dock-action" onClick={() => onDemo('佩丽卡怎么玩', 'ask')}><span className="dock-symbol" aria-hidden="true">✳</span><span><small>KNOWLEDGE</small><b>试试知识问答</b></span><i aria-hidden="true">↗</i></button>
        </div>
      </div>
      <a className="hero-scroll" href="#search-command" aria-label="向下浏览查询区"><span>SCROLL TO EXPLORE</span><i aria-hidden="true">↓</i></a>
    </section>
  )
}
