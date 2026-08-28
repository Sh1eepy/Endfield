import { useEffect, useRef, useState } from 'react'
import type { OperatorChapter, OperatorDetail, OperatorTab, OperatorWidget } from '../types'
import { mediaSrc } from '../utils'
import { StructBlocks } from './KbCard'

// 全局唯一音频实例：切换播放时停止上一个（等价旧版 OPERATOR_AUDIO 单例）
let currentAudio: HTMLAudioElement | null = null
let currentButton: HTMLButtonElement | null = null

interface Props {
  op: OperatorDetail
  onPickName: (name: string) => void
}

/** 干员档案：hero / 章节导航 / 页签 / 事实 / 表格 / 音频 / 视频 */
export default function OperatorDossier({ op, onPickName }: Props) {
  const [activeChapter, setActiveChapter] = useState(0)
  const navRef = useRef<HTMLElement>(null)
  const thumbRef = useRef<HTMLElement>(null)

  const chapters: OperatorChapter[] = op.chapters || []
  const visual = op.illustration || op.cover || ''

  // 章节横向滚动状态条
  useEffect(() => {
    const nav = navRef.current
    const thumb = thumbRef.current
    if (!nav || !thumb) return
    const update = () => {
      const max = Math.max(0, nav.scrollWidth - nav.clientWidth)
      const visible = Math.min(1, nav.clientWidth / Math.max(nav.scrollWidth, 1))
      const progress = max ? nav.scrollLeft / max : 0
      thumb.style.width = `${Math.max(18, visible * 100)}%`
      thumb.style.transform = `translateX(${progress * (100 / Math.max(visible, 0.18) - 100)}%)`
    }
    nav.addEventListener('scroll', update, { passive: true })
    requestAnimationFrame(update)
    return () => nav.removeEventListener('scroll', update)
  }, [chapters.length])

  return (
    <div className="operator-dossier">
      <section className="operator-hero">
        <div className="operator-hero-copy">
          <div className="operator-code">OPERATOR / {op.item_id || '--'}</div>
          <h2 className="operator-name">{op.name}</h2>
          <p className="operator-caption">{op.caption || '终末地干员资料档案'}</p>
        </div>
        {visual ? (
          <img className="operator-visual" src={mediaSrc(visual)} alt={op.name} />
        ) : null}
      </section>

      <nav className="operator-chapter-nav" aria-label="干员详情章节" ref={navRef}>
        {chapters.map((c, i) => (
          <button
            key={c.title}
            type="button"
            className={`operator-nav-btn${i === activeChapter ? ' active' : ''}`}
            data-op-chapter={i}
            onClick={() => setActiveChapter(i)}
          >
            {c.title}
          </button>
        ))}
      </nav>
      <div className="operator-scroll-status">
        <span>SWIPE / LEFT</span>
        <div className="operator-scroll-track"><i className="operator-scroll-thumb" ref={thumbRef} /></div>
        <span>RIGHT / DRAG</span>
      </div>

      <div className="operator-chapters">
        {chapters.map((chapter, ci) => (
          <section
            key={ci}
            className={`operator-chapter${ci === activeChapter ? ' active' : ''}`}
            data-op-panel={ci}
          >
            {(chapter.widgets || []).map((widget, wi) => (
              <OperatorWidget
                key={`${ci}-${wi}`}
                widget={widget}
                widgetIndex={wi}
                onPickName={onPickName}
              />
            ))}
          </section>
        ))}
      </div>
    </div>
  )
}

function OperatorWidget({ widget, widgetIndex, onPickName }: {
  widget: OperatorWidget
  widgetIndex: number
  onPickName: (name: string) => void
}) {
  const [activeTab, setActiveTab] = useState(0)
  const tabs: OperatorTab[] = widget.tabs || []
  const showTabs = tabs.length > 1 || Boolean(tabs[0]?.icon)

  return (
    <article className="operator-widget">
      <div className="operator-widget-title">
        <h3>{widget.title}</h3>
        <span>{widget.type || 'DATA'} / {String(widgetIndex + 1).padStart(2, '0')}</span>
      </div>

      {widget.facts && widget.facts.length ? (
        <div className="operator-facts">
          {widget.facts.map((f, i) => (
            <div key={i} className="operator-fact">
              <div className="operator-fact-label">{f.label}</div>
              <div className="operator-fact-value">{f.value}</div>
            </div>
          ))}
        </div>
      ) : null}

      {tabs.length ? (
        <>
          {showTabs ? (
            <div className="operator-tabs" role="tablist">
              {tabs.map((t, ti) => (
                <button
                  key={ti}
                  type="button"
                  className={`operator-tab-btn${ti === activeTab ? ' active' : ''}${t.icon ? ' has-icon' : ''}`}
                  data-op-tab={`op-${widgetIndex}`}
                  data-tab-index={ti}
                  title={t.title}
                  onClick={() => setActiveTab(ti)}
                >
                  {t.icon ? <img src={mediaSrc(t.icon)} alt="" /> : t.title}
                </button>
              ))}
            </div>
          ) : null}
          {tabs.map((tab, ti) => (
            <div
              key={ti}
              className={`operator-pane${ti === activeTab ? ' active' : ''}`}
              data-tab-panel={`op-${widgetIndex}`}
              data-tab-index={ti}
            >
              {tab.intro ? (
                <div className="operator-intro">
                  {tab.intro.imgUrl
                    ? <img src={mediaSrc(tab.intro.imgUrl)} alt={tab.intro.name || tab.title} />
                    : <div />}
                  <div>
                    <h4>{tab.intro.name || tab.title}</h4>
                    <div className="operator-intro-type">{tab.intro.type || 'OPERATOR DATA'}</div>
                    <p>{tab.intro.description || ''}</p>
                  </div>
                </div>
              ) : null}
              {tab.blocks && tab.blocks.length ? (
                <StructBlocks blocks={tab.blocks} onPickName={onPickName} />
              ) : null}
              {tab.audios && tab.audios.length ? (
                <AudioList audios={tab.audios} />
              ) : null}
              {(!tab.blocks || !tab.blocks.length) && (!tab.audios || !tab.audios.length) ? (
                <div className="operator-empty">该页签暂无公开内容</div>
              ) : null}
            </div>
          ))}
        </>
      ) : null}
    </article>
  )
}

function AudioList({ audios }: { audios: { url: string; title: string; profile: string }[] }) {
  const [playingKey, setPlayingKey] = useState<string | null>(null)

  const play = async (key: string, url: string, btn: HTMLButtonElement) => {
    if (currentAudio && currentButton === btn && !currentAudio.paused) {
      currentAudio.pause()
      currentButton.classList.remove('playing')
      currentButton.textContent = '▶'
      setPlayingKey(null)
      return
    }
    if (currentAudio) currentAudio.pause()
    if (currentButton) { currentButton.classList.remove('playing'); currentButton.textContent = '▶' }
    currentAudio = new Audio(mediaSrc(url))
    currentButton = btn
    currentAudio.preload = 'none'
    btn.classList.add('playing')
    btn.textContent = 'Ⅱ'
    setPlayingKey(key)
    currentAudio.addEventListener('ended', () => {
      btn.classList.remove('playing'); btn.textContent = '▶'; setPlayingKey(null)
    })
    currentAudio.addEventListener('error', () => {
      btn.classList.remove('playing'); btn.textContent = '!'; btn.title = '音频加载失败'; setPlayingKey(null)
    })
    try {
      await currentAudio.play()
    } catch {
      btn.classList.remove('playing'); btn.textContent = '!'; setPlayingKey(null)
    }
  }

  return (
    <div className="operator-audio-list">
      {audios.map((a, i) => (
        <div key={i} className="operator-audio">
          <button
            type="button"
            className={`audio-play${playingKey === `${i}` ? ' playing' : ''}`}
            aria-label={`播放 ${a.title}`}
            onClick={(ev) => play(`${i}`, a.url, ev.currentTarget)}
          >
            {playingKey === `${i}` ? 'Ⅱ' : '▶'}
          </button>
          <div className="audio-title">{a.title}</div>
          <div className="audio-profile">{a.profile}</div>
        </div>
      ))}
    </div>
  )
}
