import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchAsk, fetchHealth, fetchNames, fetchSynthesis } from './api'
import EntryCurtain from './components/EntryCurtain'
import TopBar from './components/TopBar'
import Hero from './components/Hero'
import SearchBox from './components/SearchBox'
import SideRail from './components/SideRail'
import ResultPanel from './components/ResultPanel'
import Tip, { type TipState } from './components/Tip'
import { clearHistory, getHistory, recordHistory, type HistoryEntry } from './utils'
import type { AskResult, SynthesisResponse } from './types'

export type Mode = 'syn' | 'ask'
export type ResultState = 'empty' | 'loading' | 'ready' | 'error'

export interface SynResult {
  kind: 'syn'
  data: SynthesisResponse
  query: string
}

export interface AskLoadResult {
  kind: 'ask'
  data: AskResult
  query: string
}

export type LoadResult = SynResult | AskLoadResult

export default function App() {
  const [mode, setMode] = useState<Mode>('syn')
  const [modeQueries, setModeQueries] = useState<{ syn: string; ask: string }>({ syn: '', ask: '' })
  const [inputValue, setInputValue] = useState('')
  const [result, setResult] = useState<LoadResult | null>(null)
  const [resultState, setResultState] = useState<ResultState>('empty')
  const [errorMsg, setErrorMsg] = useState('')
  const [title, setTitle] = useState('配方合成树')
  const [apiConnected, setApiConnected] = useState(false)
  const [names, setNames] = useState<string[]>([])
  const [history, setHistory] = useState<HistoryEntry[]>(getHistory())
  const [tip, setTip] = useState<TipState | null>(null)

  // 当前页面会话按 query 缓存完整回答：模式切换只重绘缓存，不重复调用 LLM。
  const askCacheRef = useRef(new Map<string, AskResult>())
  // 每次查询/清空都会使旧请求失效，避免迟到的响应覆盖当前模式与结果。
  const requestSeqRef = useRef(0)
  // 结果区入场动画计时器
  const enterTimerRef = useRef<number | null>(null)
  // 结果区容器（用于重放入场动画）
  const synTreeRef = useRef<HTMLDivElement>(null)

  useEffect(() => () => {
    requestSeqRef.current += 1
    if (enterTimerRef.current) window.clearTimeout(enterTimerRef.current)
  }, [])

  useEffect(() => {
    fetchHealth()
      .then(() => setApiConnected(true))
      .catch(() => setApiConnected(false))
    fetchNames()
      .then((d) => setNames(d.names || []))
      .catch(() => { /* 联想不可用时静默 */ })
  }, [])

  // 分区进入视口时播放一次（等价旧版 reveal-on-scroll + IntersectionObserver）
  useEffect(() => {
    const targets = document.querySelectorAll('.reveal-on-scroll')
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        })
      }, { threshold: 0.08, rootMargin: '0px 0px -5% 0px' })
      targets.forEach((el) => observer.observe(el))
      return () => observer.disconnect()
    }
    targets.forEach((el) => el.classList.add('is-visible'))
  }, [])

  // 滚动视差：设置 --scroll-y 供 CSS 使用，顶栏超过 54px 收缩（等价旧版 scroll 监听）
  useEffect(() => {
    let ticking = false
    const onScroll = () => {
      if (ticking) return
      ticking = true
      requestAnimationFrame(() => {
        const y = window.scrollY || 0
        document.documentElement.style.setProperty('--scroll-y', String(y))
        document.body.classList.toggle('is-scrolled', y > 54)
        ticking = false
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const playEnter = useCallback(() => {
    const el = synTreeRef.current
    if (!el) return
    el.classList.remove('is-entering')
    void el.offsetWidth
    el.classList.add('is-entering')
    if (enterTimerRef.current) window.clearTimeout(enterTimerRef.current)
    enterTimerRef.current = window.setTimeout(() => el.classList.remove('is-entering'), 460)
  }, [])

  const setLoading = useCallback((t: string) => {
    setResult(null)
    setResultState('loading')
    setErrorMsg('')
    setTitle(t)
  }, [])

  const setReady = useCallback((r: LoadResult, t: string) => {
    setResult(r)
    setResultState('ready')
    setErrorMsg('')
    setTitle(t)
    playEnter()
  }, [playEnter])

  const setError = useCallback((msg: string, t: string) => {
    setResult(null)
    setResultState('error')
    setErrorMsg(msg)
    setTitle(t)
  }, [])

  const showEmpty = useCallback((m: Mode) => {
    setResult(null)
    setResultState('empty')
    setErrorMsg('')
    setTitle(m === 'ask' ? '知识问答' : '配方合成树')
  }, [])

  const runQuery = useCallback((raw: string, m: Mode = mode) => {
    const q = String(raw || '').trim()
    const requestId = ++requestSeqRef.current
    const isCurrent = () => requestId === requestSeqRef.current
    setModeQueries((prev) => ({ ...prev, [mode]: inputValue, [m]: q }))
    setInputValue(q)
    setMode(m)
    if (!q) { showEmpty(m); return }
    if (m === 'syn') {
      setLoading(`${q} · 配方树`)
      fetchSynthesis(q)
        .then((d) => {
          if (!isCurrent()) return
          if (!d.ok) { setError(d.error || '未找到', `${q} · 配方树`); return }
          recordHistory(q, 'syn')
          setHistory(getHistory())
          setReady({ kind: 'syn', data: d, query: q }, `${q} · 配方树`)
        })
        .catch((e: Error) => { if (isCurrent()) setError(e.message, `${q} · 配方树`) })
    } else {
      const cached = askCacheRef.current.get(q)
      if (cached) {
        setReady({ kind: 'ask', data: cached, query: q }, `${q} · 知识问答`)
        return
      }
      setLoading(`${q} · 知识问答`)
      fetchAsk(q)
        .then((d) => {
          // 成功的旧回答可留作缓存，但不允许更新当前页面。
          if (d.ok) askCacheRef.current.set(q, d)
          if (!isCurrent()) return
          if (!d.ok) { setError(d.error || '问答失败', `${q} · 知识问答`); return }
          recordHistory(q, 'ask')
          setHistory(getHistory())
          setReady({ kind: 'ask', data: d, query: q }, `${q} · 知识问答`)
        })
        .catch((e: Error) => { if (isCurrent()) setError(e.message, `${q} · 知识问答`) })
    }
  }, [inputValue, mode, setError, setLoading, setReady, showEmpty])

  const switchMode = useCallback((m: Mode) => {
    if (m === mode) return
    runQuery(modeQueries[m] ?? '', m)
  }, [mode, modeQueries, runQuery])

  const handleHistoryPick = useCallback((entry: HistoryEntry) => {
    runQuery(entry.q, entry.mode)
  }, [runQuery])

  const openEntry = useCallback((name: string) => runQuery(name, 'syn'), [runQuery])

  const handleClearHistory = useCallback(() => {
    clearHistory()
    setHistory([])
  }, [])

  const showTip = useCallback((x: number, y: number, content: ReactNode) => {
    setTip({ x, y, content })
  }, [])

  const hideTip = useCallback(() => setTip(null), [])

  return (
    <>
      <EntryCurtain />
      <div className="ambient" aria-hidden="true">
        <i className="geo geo-a" /><i className="geo geo-b" /><i className="geo geo-c" />
        <i className="geo geo-d" /><i className="geo geo-e" /><i className="geo geo-f" />
        <i className="geo geo-g" /><i className="geo geo-h" />
        <img className="bg-mascot bg-char-1" src="/assets/mascots/mascot-02.png" alt="" />
        <img className="bg-mascot bg-char-2" src="/assets/mascots/mascot-04.png" alt="" />
        <img className="bg-mascot bg-char-3" src="/assets/mascots/mascot-05.png" alt="" />
        <img className="bg-mascot bg-char-4" src="/assets/mascots/mascot-06.png" alt="" />
        <img className="bg-mascot bg-char-5" src="/assets/mascots/mascot-07.png" alt="" />
      </div>

      <TopBar connected={apiConnected} />

      <main className="site-main">
        <Hero onDemo={runQuery} />
        <SearchBox
          mode={mode}
          inputValue={inputValue}
          onInputChange={setInputValue}
          onRunQuery={runQuery}
          onModeChange={switchMode}
          names={names}
          history={history}
          onHistoryPick={handleHistoryPick}
          onClearHistory={handleClearHistory}
        />
        <section className="workspace reveal-on-scroll">
          <SideRail />
          <ResultPanel
            mode={mode}
            title={title}
            state={resultState}
            errorMsg={errorMsg}
            result={result}
            onPickName={openEntry}
            onRunQuery={runQuery}
            showTip={showTip}
            hideTip={hideTip}
            synTreeRef={synTreeRef}
          />
        </section>
        <div className="footer-line reveal-on-scroll">
          <span>© ENDFIELD SYNTHESIS ARCHIVE / COMMUNITY TOOL</span>
          <span>图片素材来自：呵纹Hevon · 画师：仓鼠饭团c</span>
          <span>DATA INTEGRITY: VERIFIED · LOCAL INDEX: ONLINE</span>
        </div>
      </main>

      <Tip tip={tip} />
    </>
  )
}
