import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Mode, ResultState } from '../App'
import type { ArchiveScene } from '../scene/archiveScene'
import { TransitionCoordinator } from '../scene/transition'
import RetrievalStatus from './RetrievalStatus'

/** One spatial environment surrounds both real query and result interfaces. */
export default function ArchiveExperience({ mode, children, query, home, resultState = 'empty', hasContent = false, resultIdentity = '', onStop, streaming = false, phase }: {
  mode: Mode; children?: ReactNode; query?: ReactNode; home?:ReactNode; resultState?: ResultState; hasContent?: boolean; resultIdentity?: string; onStop?:()=>void; streaming?:boolean; phase?:string
}) {
  const stage = useRef<HTMLDivElement>(null)
  const host = useRef<HTMLDivElement>(null)
  const queryRegion = useRef<HTMLDivElement>(null)
  const scene = useRef<ArchiveScene | null>(null)
  const coordinator = useRef(new TransitionCoordinator(mode === 'ask' ? 1 : 0))
  const [staticView, setStaticView] = useState(false)
  const [ready, setReady] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [selected, setSelected] = useState(27)
  const openRef = useRef(false)
  openRef.current = (hasContent || resultState==='error') && !dismissed
  const modeRef = useRef(mode)
  modeRef.current = mode
  useEffect(() => {
    const element = stage.current!
    const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    let disposed = false, visible = false, loading = false, failed = false
    let raf = 0, previous = 0
    const clock = coordinator.current
    const destroy = () => { scene.current?.dispose(); scene.current = null; setReady(false) }
    const activate = async () => {
      if (disposed || failed || loading || scene.current || staticView || motion?.matches || !visible || document.hidden) return
      if (!('WebGLRenderingContext' in window)) { failed = true; return }
      loading = true
      try {
        const { createArchiveScene } = await import('../scene/archiveScene')
        if (disposed || motion?.matches) return
        scene.current = createArchiveScene(host.current!, () => { failed = true; destroy() },setSelected)
        setReady(true)
        if (!raf && visible && !document.hidden) raf = requestAnimationFrame(paint)
      } catch { failed = true; destroy() }
      finally { loading = false }
    }
    const paint = (now: number) => {
      raf = 0
      if (disposed || !visible || document.hidden) return
      // Native page scrolling supplies position, not wheel velocity; one viewport ≈ 13 degrees.
      if (!openRef.current && !motion?.matches && !staticView) clock.orbit(-element.getBoundingClientRect().top / Math.max(1,window.innerHeight) * .22)
      const frame = clock.step(previous ? (now - previous) / 1000 : 1 / 60, now / 1000)
      previous = now
      const reduced = motion?.matches || staticView
      element.style.setProperty('--world-mix', frame.position.toFixed(5))
      element.style.setProperty('--travel', reduced ? '0' : frame.energy.toFixed(5))
      element.style.setProperty('--world-x', reduced ? '0' : frame.pointerX.toFixed(4))
      element.style.setProperty('--world-y', reduced ? '0' : frame.pointerY.toFixed(4))
      element.style.setProperty('--travel-direction', frame.velocity < 0 ? '-1' : '1')
      element.style.setProperty('--extract', frame.extraction.toFixed(5))
      element.dataset.reading = String(frame.extraction >= .64)
      const chapter = home ? Math.max(0, Math.min(1, 1 - (queryRegion.current?.getBoundingClientRect().top ?? 0) / window.innerHeight)) : 1
      element.style.setProperty('--chapter', chapter.toFixed(5))
      scene.current?.render(frame, chapter)
      // Visible browsing is animated; a settled open record is a still reading surface.
      if ((!reduced && !failed && frame.extraction !== 1) || frame.position !== clock.target || frame.extraction !== (openRef.current ? 1 : 0)) raf = requestAnimationFrame(paint)
    }
    const wake = () => {
      cancelAnimationFrame(raf)
      previous = 0
      if (visible && !document.hidden) { void activate(); raf = requestAnimationFrame(paint) }
    }
    const preference = () => {
      if (motion?.matches) { destroy(); clock.select(modeRef.current === 'ask' ? 1 : 0, true); clock.open(openRef.current,true) }
      wake()
    }
    const pointer = (event: PointerEvent) => {
      if (event.pointerType === 'touch' || motion?.matches || staticView || openRef.current) return
      const bounds = element.getBoundingClientRect()
      clock.point((event.clientX - bounds.left) / bounds.width * 2 - 1, (event.clientY - Math.max(0, bounds.top)) / window.innerHeight * 2 - 1)
    }
    const leave = () => { if (!openRef.current) clock.point(0, 0) }
    const changeMode = () => {
      const immediate = Boolean(motion?.matches || staticView)
      clock.select(modeRef.current === 'ask' ? 1 : 0, immediate)
      clock.open(openRef.current,immediate)
      if(openRef.current)clock.point(clock.pointerX,clock.pointerY)
      wake()
    }
    const observer = typeof IntersectionObserver !== 'undefined' ? new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; wake() }, { threshold: 0 }) : null
    if (observer) observer.observe(element)
    else { visible = true; wake() }
    element.addEventListener('experience-mode', changeMode)
    element.addEventListener('pointermove', pointer)
    element.addEventListener('pointerleave', leave)
    document.addEventListener('visibilitychange', wake)
    window.addEventListener('scroll', wake, { passive:true })
    window.addEventListener('resize', wake)
    motion?.addEventListener?.('change', preference)
    changeMode()
    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      observer?.disconnect()
      element.removeEventListener('experience-mode', changeMode)
      element.removeEventListener('pointermove', pointer)
      element.removeEventListener('pointerleave', leave)
      document.removeEventListener('visibilitychange', wake)
      window.removeEventListener('scroll', wake)
      window.removeEventListener('resize', wake)
      motion?.removeEventListener?.('change', preference)
      scene.current?.dispose()
      scene.current = null
    }
  }, [staticView])
  useEffect(() => { stage.current?.dispatchEvent(new Event('experience-mode')) }, [mode])
  useEffect(() => { setDismissed(false) }, [resultIdentity,mode,resultState])
  useEffect(() => { stage.current?.dispatchEvent(new Event('experience-mode')) }, [hasContent,dismissed,resultState])
  const browse = (amount: number) => { if(openRef.current)return; coordinator.current.scroll(amount); stage.current?.dispatchEvent(new Event('experience-mode')) }
  const drag = useRef<{y:number;travel:number}|null>(null)
  return <div ref={stage} className="archive-experience" data-view={mode} data-static={staticView} data-detail={(hasContent || resultState==='error') && !dismissed} data-state={resultState}>
    <div className="world-layer" aria-hidden="true"><div className="world-sticky">
      <div className="experience-art art-terrain" /><div className="experience-art art-signal" />
      <div className="experience-art art-query" />
      <div ref={host} className={`experience-scene${ready && !staticView ? ' is-ready' : ''}`} />
      <div className="world-vignette" />
      <div className="world-coordinate">ENDFIELD / TALOS-II<br />SPATIAL ARCHIVE SYSTEM</div>
    </div></div>
    {home}
    {home && <div className="archive-bridge" aria-hidden="true"><div className="bridge-rail" /><span>FIELD / ARCHIVE</span><b>从开拓现场，进入知识深处。</b><i>↓</i><div className="bridge-contours" /></div>}
    <div ref={queryRegion} className="archive-query">
    <div className="helix-hitarea" aria-label="3D 档案阵列，可上下拖动浏览" role="region"
      onPointerDown={event=>{ if(openRef.current || event.pointerType==='touch')return; drag.current={y:event.clientY,travel:0};event.currentTarget.setPointerCapture(event.pointerId) }}
      onPointerMove={event=>{ if(!drag.current)return; const delta=event.clientY-drag.current.y;drag.current.travel+=Math.abs(delta);drag.current.y=event.clientY;browse(-delta*.012) }}
      onPointerUp={event=>{if(drag.current && drag.current.travel<6){const bounds=host.current!.getBoundingClientRect();const chosen=scene.current?.pick((event.clientX-bounds.left)/bounds.width*2-1,-(event.clientY-bounds.top)/bounds.height*2+1);if(chosen)setSelected(chosen)}drag.current=null}}
      onPointerCancel={()=>{drag.current=null}} />
    <div className="experience-content">
      <div className="experience-topline"><span>ENDFIELD INDUSTRIES <i /> INTERACTIVE ARCHIVE</span>
        <button type="button" className="experience-replay" onClick={()=>window.dispatchEvent(new Event('endfield-replay-entry'))}>重播入场</button>
        <button type="button" className="experience-quality" aria-pressed={staticView} onClick={() => { setReady(false); setStaticView(v => !v) }} title="静态场景关闭实时渲染，不影响查询">{staticView ? '静态场景 · 开启 3D' : '实时空间 · 切为静态'} <span aria-hidden="true">↗</span></button>
      </div>
      <header className="experience-heading">
        <div className="experience-copy">
          <span className="experience-kicker">{mode === 'syn' ? '01 / MATERIAL SYNTHESIS' : '02 / KNOWLEDGE RETRIEVAL'}</span>
          <div className="experience-titles" aria-live="polite">
            <h2 className="title-syn" aria-hidden={mode !== 'syn'}><span>解析构成</span><span>延展可能<span className="title-dot">.</span></span></h2>
            <h2 className="title-ask" aria-hidden={mode !== 'ask'}><span>循着线索</span><span>连接未知<span className="title-dot">.</span></span></h2>
          </div>
          <p>{mode === 'syn' ? '每一种创造，都有迹可循。' : '从一个问题，抵达有据可循的答案。'}</p>
        </div>
        <div className="experience-callout"><span>ARCHIVE HELIX / {String(selected).padStart(2,'0')}</span><b>双螺旋档案阵列</b><small>拖动阵列上下浏览 · 点击选择展示载体</small><div className="helix-browse"><button type="button" onClick={()=>browse(-2)} aria-label="向上浏览档案">↑</button><button type="button" onClick={()=>browse(2)} aria-label="向下浏览档案">↓</button></div></div>
      </header>
      <div className="experience-workbench">{query}</div>
      <div className="archive-status">
        <RetrievalStatus active={streaming || resultState==='loading' || (resultState==='ready'&&!hasContent)} phase={phase} identity={resultIdentity} />
        {!streaming && resultState!=='loading' && !openRef.current && (hasContent ? '档案内容已就绪' : resultState==='error' ? '请求未完成，请查看错误提示。' : '输入查询，结果将从阵列中的档案盒展开。展示载体不与知识条目预先绑定。')}
        {streaming && onStop && <button type="button" onClick={onStop}>停止生成</button>}
        {hasContent && dismissed && <button type="button" onClick={()=>setDismissed(false)}>重新打开档案 ↗</button>}
        {hasContent && !dismissed && <button className="archive-skip-extract" type="button" onClick={()=>{coordinator.current.open(true,true)}}>跳过抽取 · 立即阅读</button>}
      </div>
      <div className="archive-detail" aria-hidden={dismissed || (!hasContent && resultState!=='error')}>
        <div className="archive-detail-bar"><span>ENDFIELD / {mode==='syn'?'SYNTHESIS RECORD':'KNOWLEDGE RECORD'}</span><button type="button" onClick={()=>{setDismissed(true);stage.current?.querySelector<HTMLInputElement>('#in-search')?.focus({preventScroll:true})}}>收回档案 ↙</button></div>
        {children}
      </div>
      <div className="experience-footnote"><span>LOCAL KNOWLEDGE / VERIFIED SOURCES</span><span>探索档案 <b>↗</b></span></div>
    </div>
    </div>
  </div>
}
