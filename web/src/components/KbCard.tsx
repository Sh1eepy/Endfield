import { useEffect, useRef } from 'react'
import type { Inline, KbEntry, StructBlock } from '../types'
import { mediaSrc } from '../utils'
import OperatorDossier from './OperatorDossier'

interface Props {
  kb: KbEntry
  onPickName: (name: string) => void
}

/** inline 元素：text（含颜色/粗斜体）/ entry（物品引用卡）/ link（外链）/ img */
function InlineNodes({ c, mediaMode = false, onPickName }: { c: Inline[]; mediaMode?: boolean; onPickName: (n: string) => void }) {
  return (
    <>
      {(c || []).map((e, i) => {
        if (e.t === 'text') {
          const tone = String(e.color || '').replace(/^light_/, '').replaceAll('_', '-')
          const cls = tone ? `tone-${tone}` : ''
          let node: React.ReactNode = e.x
          if (e.b) node = <strong>{node}</strong>
          if (e.i) node = <em>{node}</em>
          return <span key={i} className={cls}>{node}</span>
        }
        if (e.t === 'entry') {
          return (
            <span key={i} className="kb-entry" title="点击查看合成树" onClick={() => onPickName(e.x)}>
              {e.img ? <img className="kb-entry-icon" src={mediaSrc(e.img)} alt="" loading="lazy" /> : null}
              {e.x}
              {e.c ? <em className="cnt">×{e.c}</em> : null}
            </span>
          )
        }
        if (e.t === 'link') {
          return (
            <a key={i} className="kb-link" href={e.u} target="_blank" rel="noopener">{e.x}</a>
          )
        }
        if (e.t === 'img') {
          return (
            <img
              key={i}
              className={mediaMode ? 'kb-media-img' : 'kb-inline-img'}
              src={mediaSrc(e.u)}
              loading="lazy"
              alt=""
            />
          )
        }
        return null
      })}
    </>
  )
}

/** 表格容器：真表格 + 可拖拽横向滚动条 */
function TableFrame({ rows, onPickName }: { rows: Inline[][][]; onPickName: (n: string) => void }) {
  const frameRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const frame = frameRef.current
    if (!frame || frame.dataset.scrollBound) return
    frame.dataset.scrollBound = '1'
    const viewport = frame.querySelector<HTMLDivElement>('.kb-table-wrap')
    const track = frame.querySelector<HTMLDivElement>('.kb-table-track')
    const thumb = frame.querySelector<HTMLDivElement>('.kb-table-thumb')
    if (!viewport || !track || !thumb) return

    const update = () => {
      const max = Math.max(0, viewport.scrollWidth - viewport.clientWidth)
      const visible = Math.min(1, viewport.clientWidth / Math.max(viewport.scrollWidth, 1))
      const thumbRatio = Math.max(0.12, visible)
      const progress = max ? viewport.scrollLeft / max : 0
      thumb.style.width = `${thumbRatio * 100}%`
      thumb.style.transform = `translateX(${progress * (100 / thumbRatio - 100)}%)`
      frame.classList.toggle('is-scrollable', max > 1)
      frame.classList.toggle('is-static', max <= 1)
    }
    const seek = (ev: PointerEvent) => {
      const rect = track.getBoundingClientRect()
      const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / Math.max(rect.width, 1)))
      viewport.scrollLeft = ratio * Math.max(0, viewport.scrollWidth - viewport.clientWidth)
    }
    let dragging = false
    const onDown = (ev: PointerEvent) => { dragging = true; track.setPointerCapture(ev.pointerId); seek(ev) }
    const onMove = (ev: PointerEvent) => { if (dragging) seek(ev) }
    const onUp = (ev: PointerEvent) => { dragging = false; track.releasePointerCapture(ev.pointerId) }
    track.addEventListener('pointerdown', onDown)
    track.addEventListener('pointermove', onMove)
    track.addEventListener('pointerup', onUp)
    track.addEventListener('pointercancel', () => { dragging = false })
    viewport.addEventListener('scroll', update, { passive: true })
    const ro = new ResizeObserver(update)
    ro.observe(viewport)
    requestAnimationFrame(update)
    return () => {
      track.removeEventListener('pointerdown', onDown)
      track.removeEventListener('pointermove', onMove)
      track.removeEventListener('pointerup', onUp)
      track.removeEventListener('pointercancel', () => { dragging = false })
      viewport.removeEventListener('scroll', update)
      ro.disconnect()
    }
  }, [])

  return (
    <div className="kb-table-frame" ref={frameRef}>
      <div className="kb-table-wrap" tabIndex={0} aria-label="可横向滑动的数据表格">
        <table className="kb-table">
          <tbody>
            {(rows || []).map((row, ri) => (
              <tr key={ri}>
                {(row || []).map((cell, ci) => (
                  <td key={ci} className={ri === 0 ? 'th' : ''}>
                    <InlineNodes c={cell} onPickName={onPickName} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="kb-table-status">
        <span>LEFT</span>
        <div className="kb-table-track"><i className="kb-table-thumb" /></div>
        <span>RIGHT</span>
      </div>
    </div>
  )
}

/** 结构化块：para / img / table / hr / video */
export function StructBlocks({ blocks, onPickName }: { blocks: StructBlock[]; onPickName: (n: string) => void }) {
  return (
    <>
      {(blocks || []).map((b, bi) => {
        if (b.t === 'para') {
          const kind = b.kind === 'heading3' ? ' kb-heading3' : ''
          const align = b.align === 'center' ? ' kb-center' : ''
          if (!b.c || !b.c.length) return null
          return (
            <div key={bi} className={`kb-paragraph${kind}${align}`}>
              <InlineNodes c={b.c} onPickName={onPickName} />
            </div>
          )
        }
        if (b.t === 'img') {
          return (
            <figure key={bi} className="kb-img-wrap">
              <img className="kb-img" src={mediaSrc(b.u)} alt={b.alt || ''} loading="lazy" />
              {b.alt ? <figcaption>{b.alt}</figcaption> : null}
            </figure>
          )
        }
        if (b.t === 'table') {
          const cells = (b.r || []).flat().filter((cell) => Array.isArray(cell) && cell.length)
          const imageCount = cells.reduce((n, cell) => n + cell.filter((e) => e.t === 'img').length, 0)
          const dataCount = cells.reduce((n, cell) => n + cell.filter((e) => e.t === 'text' || e.t === 'entry').length, 0)
          const mediaTable = imageCount >= 2 && imageCount >= dataCount
          if (mediaTable) {
            return (
              <div key={bi} className="operator-media-grid" data-media-gallery="true">
                {cells.map((cell, ci) => (
                  <figure key={ci} className="operator-media-card">
                    <InlineNodes c={cell} mediaMode onPickName={onPickName} />
                  </figure>
                ))}
              </div>
            )
          }
          return <TableFrame key={bi} rows={b.r || []} onPickName={onPickName} />
        }
        if (b.t === 'hr') {
          return <div key={bi} className="kb-hr" />
        }
        if (b.t === 'video') {
          const videoUrl = `https://www.skland.com/article?id=${encodeURIComponent(b.id)}`
          return (
            <div key={bi} className="operator-video">
              <div className="operator-video-icon">▶</div>
              <div><b>森空岛视频内容</b><span>VIDEO ID / {b.id}</span></div>
              <a href={videoUrl} target="_blank" rel="noopener">打开演示视频 ↗</a>
            </div>
          )
        }
        return null
      })}
    </>
  )
}

/** 知识库卡片：无配方物品的信息展示（结构化渲染） */
export default function KbCard({ kb, onPickName }: Props) {
  if (kb.operator_detail) {
    return <OperatorDossier op={kb.operator_detail} onPickName={onPickName} />
  }
  const ss = kb.sections_struct || {}
  const secs = kb.sections || {}
  const keys = Object.keys(ss).length ? Object.keys(ss) : Object.keys(secs)
  const titles = keys.slice(0, 8)
  return (
    <div>
      <div style={{ color: 'var(--sub)', margin: '8px 0 12px', fontSize: 14 }}>
        「<b style={{ color: 'var(--accent3)' }}>{kb.name}</b>」无流水线配方，来自 WIKI 知识库：
      </div>
      {kb.category ? <span className="src-chip" style={{ marginBottom: 8 }}>{kb.category}</span> : null}
      {titles.map((k) => (
        <div key={k} className="msg bot kb-sec">
          <b style={{ color: 'var(--klein)' }}>{k}</b>
          {ss[k] && ss[k].length
            ? <StructBlocks blocks={ss[k]} onPickName={onPickName} />
            : <><br />{secs[k] || ''}</>}
        </div>
      ))}
      {!titles.length && kb.full_text ? (
        <div className="msg bot">{kb.full_text}</div>
      ) : null}
    </div>
  )
}
