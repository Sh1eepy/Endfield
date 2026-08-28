import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Mode } from '../App'
import type { HistoryEntry } from '../utils'

interface Props {
  mode: Mode
  inputValue: string
  onInputChange: (v: string) => void
  onRunQuery: (q: string, m?: Mode) => void
  onModeChange: (m: Mode) => void
  names: string[]
  history: HistoryEntry[]
  onHistoryPick: (e: HistoryEntry) => void
  onClearHistory: () => void
}

const SUGGEST_LIMIT = 14

/** 搜索框：模式切换 / 输入联想 / 键盘导航 / 历史记录。 */
export default function SearchBox({
  mode, inputValue, onInputChange, onRunQuery, onModeChange,
  names, history, onHistoryPick, onClearHistory,
}: Props) {
  const [suggestList, setSuggestList] = useState<string[]>([])
  const [suggestVisible, setSuggestVisible] = useState(false)
  const [suggestIndex, setSuggestIndex] = useState(-1)
  const wrapRef = useRef<HTMLDivElement>(null)

  // 输入变化 → 前缀优先 + 包含匹配
  const handleInput = useCallback((value: string) => {
    onInputChange(value)
    const q = value.trim()
    setSuggestIndex(-1)
    if (!q) { setSuggestVisible(false); return }
    const starts = names.filter((n) => n.startsWith(q))
    const contains = names.filter((n) => n.includes(q) && !n.startsWith(q))
    setSuggestList([...starts, ...contains].slice(0, SUGGEST_LIMIT))
    setSuggestVisible(true)
  }, [names, onInputChange])

  const hideSuggest = useCallback(() => {
    setSuggestVisible(false)
    setSuggestIndex(-1)
  }, [])

  const pickSuggestion = useCallback((name: string) => {
    onInputChange(name)
    hideSuggest()
    onRunQuery(name)
  }, [hideSuggest, onInputChange, onRunQuery])

  const handleKeyDown = useCallback((ev: React.KeyboardEvent<HTMLInputElement>) => {
    if (ev.key === 'ArrowDown') {
      ev.preventDefault()
      setSuggestIndex((i) => Math.min(i + 1, suggestList.length - 1))
    } else if (ev.key === 'ArrowUp') {
      ev.preventDefault()
      setSuggestIndex((i) => Math.max(i - 1, 0))
    } else if (ev.key === 'Enter') {
      ev.preventDefault()
      if (suggestList[suggestIndex]) pickSuggestion(suggestList[suggestIndex])
      else { hideSuggest(); onRunQuery(inputValue) }
    }
  }, [hideSuggest, inputValue, onRunQuery, pickSuggestion, suggestIndex, suggestList])

  // 点击外部关闭联想
  useEffect(() => {
    function onClick(ev: MouseEvent) {
      if (!wrapRef.current?.contains(ev.target as Node)) hideSuggest()
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [hideSuggest])

  // 高亮匹配子串
  const highlight = useMemo(() => (name: string) => {
    const q = inputValue.trim()
    const idx = name.indexOf(q)
    if (idx < 0) return name
    return (
      <>
        {name.slice(0, idx)}
        <b style={{ color: 'var(--accent3)' }}>{name.slice(idx, idx + q.length)}</b>
        {name.slice(idx + q.length)}
      </>
    )
  }, [inputValue])

  return (
    <div className="search-wrap command-shell" ref={wrapRef}>
      <img className="frame-mascot mascot-search" src="/assets/mascots/mascot-01.png" alt="" />
      <div className="command-head">
        <div className="mode-tabs" id="mode-tabs">
          <button
            type="button"
            className={`mode-btn${mode === 'syn' ? ' active' : ''}`}
            data-mode="syn"
            data-index="01"
            onClick={() => onModeChange('syn')}
          >
            配方合成树
          </button>
          <button
            type="button"
            className={`mode-btn${mode === 'ask' ? ' active' : ''}`}
            data-mode="ask"
            data-index="02"
            onClick={() => onModeChange('ask')}
          >
            知识问答
          </button>
        </div>
        <div className="mode-note"><strong>●</strong> SELECT OPERATION MODE</div>
      </div>
      <div className="query-row">
        <span className="query-prefix">QUERY://</span>
        <input
          id="in-search"
          aria-label="搜索物品、设备或知识问题"
          placeholder="输入物品、设备名或直接提问…"
          autoComplete="off"
          value={inputValue}
          onChange={(ev) => handleInput(ev.target.value)}
          onKeyDown={handleKeyDown}
        />
        <span className="enter-key">ENTER ↵</span>
      </div>
      <div id="suggest" className={suggestVisible ? 'visible' : ''}>
        {suggestVisible && (
          suggestList.length === 0 ? (
            <div className="sug-empty">没有匹配「{inputValue.trim()}」的名称</div>
          ) : (
            suggestList.map((n, i) => (
              <div
                key={n}
                className={`sug-item${i === suggestIndex ? ' active' : ''}`}
                onMouseDown={(ev) => { ev.preventDefault(); pickSuggestion(n) }}
              >
                {highlight(n)}
              </div>
            ))
          )
        )}
      </div>
      <div id="search-history" className="search-history">
        {history.length > 0 && (
          <>
            <span className="history-label">最近查询</span>
            {history.map((x) => (
              <button
                key={`${x.q}-${x.mode}`}
                className="history-chip"
                title={x.mode === 'ask' ? '知识问答' : '配方合成树'}
                onClick={() => onHistoryPick(x)}
              >
                {x.q}
              </button>
            ))}
            <button className="history-clear" title="仅清除本浏览器记录" onClick={onClearHistory}>清除</button>
          </>
        )}
      </div>
    </div>
  )
}
