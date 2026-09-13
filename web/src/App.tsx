import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  fetchAsk, fetchAskStream, fetchHealth, fetchNames, fetchSynthesis,
  StreamUnavailableError, type AskStreamEvent,
} from './api'
import EntryCurtain from './components/EntryCurtain'
import TopBar from './components/TopBar'
import Hero from './components/Hero'
import SearchBox from './components/SearchBox'
import SideRail from './components/SideRail'
import ArchiveExperience from './components/ArchiveExperience'
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
  // 流式问答：AbortController 用于切换/离开时中断旧请求。
  const askStreamRef = useRef<{ controller: AbortController | null }>({ controller: null })
  // 结果区入场动画计时器
  const enterTimerRef = useRef<number | null>(null)
  // 结果区容器（用于重放入场动画）
  const synTreeRef = useRef<HTMLDivElement>(null)

  useEffect(() => () => {
    requestSeqRef.current += 1
    askStreamRef.current.controller?.abort()
    askStreamRef.current.controller = null
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

  const stopAskStream = useCallback(() => {
    askStreamRef.current.controller?.abort()
    askStreamRef.current.controller = null
  }, [])

  const handleStopAsk = useCallback(() => {
    requestSeqRef.current += 1
    stopAskStream()
    setResult((current) => {
      if (current?.kind !== 'ask' || !current.data.streaming) return current
      return { ...current, data: { ...current.data, streaming: false,
        stream_error: current.data.answer ? '已停止生成，已保留当前内容。' : '已停止生成。' } }
    })
  }, [stopAskStream])

  /** 知识问答走 /api/ask/stream：先亮阶段/来源，答案逐段追加；旧后端自动回退整包。 */
  const runAskStream = useCallback((q: string, isCurrent: () => boolean) => {
    stopAskStream()
    const cached = askCacheRef.current.get(q)
    if (cached) {
      setReady({ kind: 'ask', data: cached, query: q }, `${q} · 知识问答`)
      return
    }
    setLoading(`${q} · 知识问答`)
    const controller = new AbortController()
    askStreamRef.current.controller = controller
    let partial: AskResult = { ok: true, streaming: true, intent: '…', phase_text: '正在连接问答服务…' }
    let finished = false
    let commitTimer: number | null = null
    const cancelScheduled = () => {
      if (commitTimer !== null) { window.clearTimeout(commitTimer); commitTimer = null }
    }
    // 增量节流：80ms 合并一次 React 重渲染，避免每个 token 全量渲染 markdown
    const schedule = () => {
      if (commitTimer !== null) return
      commitTimer = window.setTimeout(() => {
        commitTimer = null
        if (!isCurrent()) return
        setResult({ kind: 'ask', data: { ...partial }, query: q })
        setResultState('ready')
      }, 80)
    }
    const commitNow = (withEnter: boolean) => {
      cancelScheduled()
      if (!isCurrent()) return
      setResult({ kind: 'ask', data: { ...partial }, query: q })
      setResultState('ready')
      setErrorMsg('')
      if (withEnter) playEnter()
    }
    const onEvent = (ev: AskStreamEvent) => {
      if (!isCurrent() || finished) return
      if (ev.event === 'phase') {
        const text = typeof ev.data.text === 'string' ? ev.data.text : ''
        partial = { ...partial, phase_text: text || partial.phase_text }
        schedule()
      } else if (ev.event === 'meta') {
        partial = { ...partial, ...(ev.data as unknown as AskResult), streaming: true }
        schedule()
      } else if (ev.event === 'delta') {
        partial = { ...partial, answer: (partial.answer || '') + String(ev.data.text ?? '') }
        schedule()
      } else if (ev.event === 'error') {
        const msg = typeof ev.data?.message === 'string' ? ev.data.message : '回答生成中断'
        if (partial.answer) {
          partial = { ...partial, streaming: false, stream_error: msg }
          commitNow(false)
        } else {
          cancelScheduled()
          finished = true
          askStreamRef.current.controller = null
          setError(msg, `${q} · 知识问答`)
        }
      } else if (ev.event === 'done') {
        const done: AskResult = { ...(ev.data as unknown as AskResult), streaming: false }
        finished = true
        askStreamRef.current.controller = null
        if (!done.ok) {
          cancelScheduled()
          setError(done.error || '问答失败', `${q} · 知识问答`)
          return
        }
        askCacheRef.current.set(q, done)
        recordHistory(q, 'ask')
        setHistory(getHistory())
        partial = done
        commitNow(true)
      }
    }
    fetchAskStream(q, onEvent, controller.signal)
      .then(() => {
        if (!isCurrent() || finished) return
        askStreamRef.current.controller = null
        // 服务端异常收尾（error 后无 done）：保留已生成内容或提示重试
        finished = true
        if (partial.answer) {
          partial = { ...partial, streaming: false,
            stream_error: partial.stream_error || '回答生成中断，已保留已生成的内容' }
          commitNow(false)
        }
        else {
          cancelScheduled()
          setError('回答生成中断，请重试', `${q} · 知识问答`)
        }
      })
      .catch((e: unknown) => {
        if (!isCurrent()) return
        askStreamRef.current.controller = null
        if (e instanceof StreamUnavailableError) {
          // 旧后端没有流式端点 → 回退整包 /api/ask
          cancelScheduled()
          fetchAsk(q)
            .then((d) => {
              if (!isCurrent()) return
              if (!d.ok) { setError(d.error || '问答失败', `${q} · 知识问答`); return }
              askCacheRef.current.set(q, d)
              recordHistory(q, 'ask')
              setHistory(getHistory())
              setReady({ kind: 'ask', data: d, query: q }, `${q} · 知识问答`)
            })
            .catch((e2: Error) => { if (isCurrent()) setError(e2.message, `${q} · 知识问答`) })
          return
        }
        if (partial.answer) {
          partial = { ...partial, streaming: false, stream_error: '网络中断，已保留已生成的内容' }
          commitNow(false)
        } else if (e instanceof Error && e.name === 'AbortError') {
          // 主动切换/离开导致的取消：页面已有新状态，不弹错误
        } else {
          cancelScheduled()
          setError(e instanceof Error ? e.message : '请求失败', `${q} · 知识问答`)
        }
      })
  }, [playEnter, setError, setHistory, setLoading, setReady, stopAskStream])

  const runQuery = useCallback((raw: string, m: Mode = mode) => {
    const q = String(raw || '').trim()
    const requestId = ++requestSeqRef.current
    const isCurrent = () => requestId === requestSeqRef.current
    setModeQueries((prev) => ({ ...prev, [mode]: inputValue, [m]: q }))
    setInputValue(q)
    setMode(m)
    if (!q) { stopAskStream(); showEmpty(m); return }
    document.getElementById('search-command')?.scrollIntoView?.({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start',
    })
    if (m === 'syn') {
      stopAskStream()
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
      runAskStream(q, isCurrent)
    }
  }, [inputValue, mode, runAskStream, setError, setLoading, setReady, showEmpty, stopAskStream])

  const switchMode = useCallback((m: Mode) => {
    if (m === mode) return
    const nextQuery = modeQueries[m] ?? ''
    requestSeqRef.current += 1
    stopAskStream()
    setModeQueries((prev) => ({ ...prev, [mode]: inputValue }))
    setInputValue(nextQuery)
    setMode(m)
    const cached = m === 'ask' && nextQuery ? askCacheRef.current.get(nextQuery) : undefined
    if (cached) setReady({ kind: 'ask', data: cached, query: nextQuery }, `${nextQuery} · 知识问答`)
    else showEmpty(m)
  }, [inputValue, mode, modeQueries, setReady, showEmpty, stopAskStream])

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

      <TopBar connected={apiConnected} />

      <main className="site-main" id="page-top">
        <ArchiveExperience mode={mode} resultState={resultState} resultIdentity={result?.query || title}
          home={<Hero onDemo={runQuery} />}
          phase={resultState==='ready' && result?.kind==='ask' ? result.data.phase_text : undefined}
          onStop={handleStopAsk} streaming={mode==='ask' && (resultState==='loading' || (result?.kind==='ask' && Boolean(result.data.streaming)))}
          hasContent={resultState === 'ready' && Boolean(result && (result.kind === 'syn' || result.data.answer || !result.data.streaming))}
          query={
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
          }>
        <section className="workspace" id="workspace">
          <SideRail mode={mode} />
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
            onStopAsk={handleStopAsk}
          />
        </section>
        </ArchiveExperience>
        <div className="footer-line reveal-on-scroll">
          <span>ENDFIELD ARCHIVE / 非官方社区工具</span>
          <span>游戏美术素材 © 鹰角网络 · 来自官方公开资料与 WIKI</span>
          <a href="#page-top">返回顶部 ↑</a>
        </div>
      </main>

      <Tip tip={tip} />
    </>
  )
}
