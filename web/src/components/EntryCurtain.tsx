import { useEffect, useState } from 'react'

/** 会话首次进入时的短开场：快速建立品牌语气，不阻塞持续查询。 */
export default function EntryCurtain() {
  const [complete, setComplete] = useState(false)
  const [progress, setProgress] = useState('000%')
  const [fillWidth, setFillWidth] = useState('0%')

  useEffect(() => {
    let seen = false
    try { seen = window.sessionStorage.getItem('endfield-entry-seen') === '1' } catch { /* storage may be disabled */ }
    if (seen || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setComplete(true)
      return
    }
    const duration = 1250
    const started = performance.now()
    let raf = 0
    let timeout = 0
    const finish = () => {
      try { window.sessionStorage.setItem('endfield-entry-seen', '1') } catch { /* storage may be disabled */ }
      setComplete(true)
    }
    // 后台标签页可能暂停 requestAnimationFrame；硬超时保证遮罩不会永久挡住查询。
    const safetyTimeout = window.setTimeout(finish, 2000)
    function frame(now: number) {
      const elapsed = Math.min(1, (now - started) / duration)
      // 快进度配合硬切遮罩，避免假装进行漫长的数据加载。
      const value = 100 * (1 - Math.pow(1 - elapsed, 2.4))
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
  }, [])

  // 入场动画期间锁定页面滚动：curtain 是全屏遮罩，滚轮不应看到下层内容
  useEffect(() => {
    if (complete) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [complete])

  return (
    <div className={`entry-curtain${complete ? ' is-complete' : ''}`} id="entry-curtain" aria-hidden="true">
      <div className="entry-mechanism">
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
            <span>ENDFIELD INDUSTRIES / INDEX LINK</span>
            <b className="entry-percent" id="entry-percent">{progress}</b>
          </div>
          <div className="entry-progress"><span className="entry-progress-fill" style={{ width: fillWidth }} /></div>
          <div className="entry-ticks" />
        </div>
      </div>
    </div>
  )
}
