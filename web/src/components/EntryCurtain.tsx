import { useCallback, useEffect, useRef, useState } from 'react'

/** 会话首次进入时的短开场：快速建立品牌语气，不阻塞持续查询。 */
export default function EntryCurtain() {
  const [complete, setComplete] = useState(false)
  const [progress, setProgress] = useState('000%')
  const [fillWidth, setFillWidth] = useState('0%')
  const [replay, setReplay] = useState(0)
  const skipRef = useRef<HTMLButtonElement>(null)
  const finish = useCallback(() => {
    try { window.sessionStorage.setItem('endfield-entry-seen', '1') } catch { /* private browsing */ }
    setComplete(true)
  }, [])
  useEffect(() => {
    const play = () => { setComplete(false); setProgress('000%'); setFillWidth('0%'); setReplay(v=>v+1) }
    window.addEventListener('endfield-replay-entry',play)
    return () => window.removeEventListener('endfield-replay-entry',play)
  }, [])

  useEffect(() => {
    if (complete) return
    let seen = false
    try { seen = window.sessionStorage.getItem('endfield-entry-seen') === '1' } catch { /* storage may be disabled */ }
    if ((seen && replay === 0) || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setComplete(true)
      return
    }
    const duration = 6000
    const started = performance.now()
    let raf = 0
    let timeout = 0
    // 后台标签页可能暂停 requestAnimationFrame；硬超时保证遮罩不会永久挡住查询。
    const safetyTimeout = window.setTimeout(finish, 8000)
    function frame(now: number) {
      const elapsed = Math.min(1, (now - started) / duration)
      // This is explicitly intro-sequence progress, not invented resource loading.
      const value = 100 * elapsed
      const whole = Math.min(100, Math.floor(value))
      // 直接内联控制宽度，进度条随数值平滑填满
      setFillWidth(`${whole}%`)
      setProgress(`${String(whole).padStart(3, '0')}%`)
      if (elapsed < 1) raf = requestAnimationFrame(frame)
      else timeout = window.setTimeout(finish, 140)
    }
    raf = requestAnimationFrame(frame)
    return () => {
      cancelAnimationFrame(raf)
      window.clearTimeout(timeout)
      window.clearTimeout(safetyTimeout)
    }
  }, [replay,finish,complete])

  // 入场动画期间锁定页面滚动：curtain 是全屏遮罩，滚轮不应看到下层内容
  useEffect(() => {
    if (complete) return
    const prev = document.body.style.overflow
    const focused = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'
    skipRef.current?.focus({preventScroll:true})
    const escape = (event: KeyboardEvent) => { if(event.key==='Escape')finish();if(event.key==='Tab'){event.preventDefault();skipRef.current?.focus()} }
    window.addEventListener('keydown',escape)
    return () => { document.body.style.overflow = prev;window.removeEventListener('keydown',escape);focused?.focus?.({preventScroll:true}) }
  }, [complete,finish])

  return (
    <div className={`entry-curtain${complete ? ' is-complete' : ''}`} id="entry-curtain" aria-hidden={complete} role={complete?undefined:'dialog'} aria-label="终末地入场动画" aria-modal={complete?undefined:true}>
      <div className="entry-mechanism" key={replay}>
        <div className="entry-access"><span>ENDFIELD INDUSTRIES</span><b>连接档案终端<span>_</span></b><small>LOCAL ARCHIVE / TALOS-II</small></div>
        <svg className="entry-orbits" viewBox="0 0 600 600" aria-hidden="true">
          {[90,145,210,265].map((r,i)=><g key={r} className={`entry-orbit orbit-${i}`}><circle cx="300" cy="300" r={r} pathLength="100" /><circle cx={300+r} cy="300" r={i%2?4:6} className="orbit-point" /></g>)}
          <path className="entry-crosshair" d="M270 300h60M300 270v60M15 300h35M550 300h35M300 15v35M300 550v35" />
        </svg>
        <div className="entry-welcome"><span>WELCOME TO THE ARCHIVE</span><h2>ENDFIELD<span>终末地 · 开拓档案</span></h2><p>从物质的构成，到知识的连接。</p><i /></div>
        <i className="entry-beam entry-beam-a" />
        <i className="entry-beam entry-beam-b" />
        <i className="entry-rail left" />
        <i className="entry-rail right" />
        <div className="entry-logo-plate">
          <i className="entry-lock left" />
          <i className="entry-lock right" />
          <img src="/assets/mascots/endfield-logo.png" alt="" />
        </div>
        <div className="entry-boot">
          <div className="entry-boot-head">
            <span>INTRO SEQUENCE / 入场演绎</span>
            <b className="entry-percent" id="entry-percent">{progress}</b>
          </div>
          <div className="entry-progress"><span className="entry-progress-fill" style={{ width: fillWidth }} /></div>
          <div className="entry-ticks" />
        </div>
      </div>
      <button ref={skipRef} type="button" className="entry-skip" onClick={finish} tabIndex={complete?-1:0}>跳过动画 <span>ESC ↗</span></button>
    </div>
  )
}
