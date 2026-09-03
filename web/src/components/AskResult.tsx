import { useEffect, useRef, useState } from 'react'
import type { AskData } from '../types'
import { submitFeedback } from '../api'
import AnswerMarkdown from './AnswerMarkdown'

const submittedTraceIds = new Set<string>()

interface Props {
  data: AskData
  query?: string
  onPickName: (name: string) => void
}

/** 结构化直查结果：配方卡 / 设备配方卡 / 歧义候选 */
function StructuredResult({ d, onPickName }: { d: AskData; onPickName: (n: string) => void }) {
  if (d.route === 'recipe' || d.route === 'device') {
    const label = d.route === 'recipe'
      ? `「${d.item}」的合成配方`
      : `设备「${d.device}」能造的配方（${(d.recipes || []).length} 个）`
    return (
      <div className="msg bot" style={{ marginTop: 10 }}>
        <b style={{ color: 'var(--accent3)' }}>{label}</b>
        {(d.recipes || []).map((r, i) => (
          <div key={i} className="ask-recipe-card">
            <div className="rc-machine">{r.machine} · {r.duration}s</div>
            <div className="rc-row"><b>原料</b>：{r.inputs.map((x) => `${x.name}×${x.count}`).join('、')}</div>
            <div className="rc-row"><b>产物</b>：{r.outputs.map((x) => `${x.name}×${x.count}`).join('、')}</div>
          </div>
        ))}
      </div>
    )
  }
  if (d.route === 'device_products') {
    return (
      <div className="msg bot" style={{ marginTop: 10 }}>
        <b style={{ color: 'var(--accent3)' }}>产出「{d.keyword}」的设备</b><br />
        {(d.matches || []).map((m, i) => (
          <span key={i} className="ask-src-chip" onClick={() => onPickName(m.device)}>
            {m.device} → {m.output}×{m.count}
          </span>
        ))}
      </div>
    )
  }
  if (d.route === 'ambiguous') {
    return (
      <div style={{ color: 'var(--sub)', margin: '10px 0' }}>
        「{d.item}」匹配多个物品，请选择：
        {(d.candidates || []).map((n) => (
          <span key={n} className="ask-ambig" onClick={() => onPickName(n)}>{n}</span>
        ))}
      </div>
    )
  }
  return null
}

/** 知识问答结果（/api/ask） */
export default function AskResult({ data, query = '', onPickName }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [feedback, setFeedback] = useState<'idle' | 'sending' | 'sent' | 'error'>(
    () => data.trace_id && submittedTraceIds.has(data.trace_id) ? 'sent' : 'idle',
  )
  useEffect(() => {
    setFeedback(data.trace_id && submittedTraceIds.has(data.trace_id) ? 'sent' : 'idle')
  }, [data.trace_id])
  if (!data.ok) return null
  const intent = data.intent || '未知'
  const structured = data.route_used === 'structured'
  const isStreaming = !!data.streaming

  const jumpToSource = (n: number) => {
    const chips = rootRef.current?.querySelectorAll<HTMLElement>('.ask-sources .ask-src-chip')
    const target = chips?.[n - 1]
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target.style.boxShadow = '0 0 0 3px rgba(79,70,229,.25)'
    }
  }

  const sendFeedback = async (vote: 'useful' | 'not_useful') => {
    if (!data.trace_id || !query || feedback === 'sending' || feedback === 'sent') return
    setFeedback('sending')
    try {
      await submitFeedback(data.trace_id, query, vote, '', data.feedback_snapshot || '')
      submittedTraceIds.add(data.trace_id)
      setFeedback('sent')
    } catch {
      setFeedback('error')
    }
  }

  return (
    <div ref={rootRef}>
      <div style={{ margin: '8px 0 4px' }}>
        <span className="ask-intent-tag">意图：{intent}</span>
        <span className="ask-intent-tag" style={{ background: 'rgba(23,55,209,.08)', color: 'var(--klein)', borderColor: 'rgba(23,55,209,.35)' }}>
          {structured ? '结构化直查' : '知识库检索'}
        </span>
      </div>

      {structured ? (
        <StructuredResult d={data} onPickName={onPickName} />
      ) : (
        <>
          {data.stream_error ? (
            <div className="ask-answer" style={{ color: 'var(--danger)', fontSize: 13, opacity: 0.85 }}>
              ⚠ {data.stream_error}
            </div>
          ) : null}
          {!data.answer && isStreaming ? (
            <div className="ask-answer ask-stream-wait" style={{ color: 'var(--faint)' }}>
              {data.phase_text || '正在生成回答…'}
              <span style={{ display: 'inline-block', marginLeft: 6, opacity: 0.9 }}>▍</span>
            </div>
          ) : data.answer ? (
            data.rejected
              ? <div className="ask-answer ask-rejected">{data.answer}</div>
              : (
                <div className="ask-answer">
                  <AnswerMarkdown answer={data.answer} onJump={jumpToSource} />
                  {isStreaming ? (
                    <span className="ask-caret" aria-hidden="true">▍</span>
                  ) : null}
                </div>
              )
          ) : (
            <div className="ask-answer ask-rejected">知识库检索完成，但回答生成暂不可用（未配置 LLM 或调用失败）。</div>
          )}

          {data.sources && data.sources.length ? (
            <div className="ask-sources">
              <div className="ask-src-title">依据来源（点击查看）</div>
              {data.sources.map((s, i) => (
                <button type="button" key={`${s.name}-${i}`} className="ask-src-chip" onClick={() => onPickName(
                  s.category === '干员语音' ? s.name.split('｜语音：')[0] : s.name,
                )}>
                  <span className="rn">[{i + 1}]</span>{s.name}
                </button>
              ))}
            </div>
          ) : null}

          {data.hits && data.hits.length ? (
            <div className="ask-hits">
              <details>
                <summary>检索片段（{data.hits.length} 条）</summary>
                {data.hits.map((h, i) => (
                  <details key={i}>
                    <summary>
                      <span className="hit-name">{h.meta.name}</span>{' '}
                      <span style={{ color: 'var(--faint)' }}>({h.meta.category})</span>
                    </summary>
                    <div className="hit-text">{h.text.slice(0, 260)}</div>
                  </details>
                ))}
              </details>
            </div>
          ) : null}
        </>
      )}
      {data.trace_id && !isStreaming ? (
        <div className="ask-feedback" aria-live="polite">
          {feedback === 'sent' ? <span>感谢反馈，已进入人工审核队列。</span> : (
            <>
              <span>{feedback === 'error' ? '反馈提交失败，请稍后重试。' : '这个回答有用吗？'}</span>
              <button type="button" disabled={feedback === 'sending'} onClick={() => sendFeedback('useful')}>有用</button>
              <button type="button" disabled={feedback === 'sending'} onClick={() => sendFeedback('not_useful')}>没用</button>
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}
