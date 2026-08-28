import { useEffect, useState } from 'react'

/** 机械开场动画：约 3.4s 进度 + 机械组件锁定，尊重 prefers-reduced-motion。 */
export default function EntryCurtain() {
  const [complete, setComplete] = useState(false)
  const [progress, setProgress] = useState('000%')
  const [fillWidth, setFillWidth] = useState('0%')

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setComplete(true)
      return
    }
    const duration = 3400
    const started = performance.now()
    let raf = 0
    let timeout = 0
    function frame(now: number) {
      const elapsed = Math.min(1, (now - started) / duration)
      // 前段稳步建立连接，中段略停顿，最后快速完成校验。
      let value: number
      if (elapsed < 0.26) value = (elapsed / 0.26) * 24
      else if (elapsed < 0.68) value = 24 + ((elapsed - 0.26) / 0.42) * 55
      else if (elapsed < 0.9) value = 79 + ((elapsed - 0.68) / 0.22) * 16
      else value = 95 + ((elapsed - 0.9) / 0.1) * 5
      const whole = Math.min(100, Math.floor(value))
      // 直接内联控制宽度，进度条随数值平滑填满
      setFillWidth(`${whole}%`)
      setProgress(`${String(whole).padStart(3, '0')}%`)
      if (elapsed < 1) raf = requestAnimationFrame(frame)
      else timeout = window.setTimeout(() => setComplete(true), 360)
    }
    raf = requestAnimationFrame(frame)
    return () => {
      cancelAnimationFrame(raf)
      window.clearTimeout(timeout)
    }
  }, [])

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
            <span>ARCHIVE CORE / MECHANICAL LINK</span>
            <b className="entry-percent" id="entry-percent">{progress}</b>
          </div>
          <div className="entry-progress"><span className="entry-progress-fill" style={{ width: fillWidth }} /></div>
          <div className="entry-ticks" />
        </div>
      </div>
    </div>
  )
}
