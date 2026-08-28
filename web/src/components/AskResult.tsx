import type { ReactNode } from 'react'
import type { AskData } from '../types'

interface Props {
  data: AskData
  onPickName: (name: string) => void
}

/** 内联 markdown：**加粗**、*斜体*、`代码` → React 节点（防 XSS，纯文本渲染） */
function inlineToNodes(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const re = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*)/g
  let last = 0
  let m: RegExpExecArray | null
  let k = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) nodes.push(<strong key={`${keyBase}-${k++}`}>{tok.slice(2, -2)}</strong>)
    else if (tok.startsWith('`')) nodes.push(<code key={`${keyBase}-${k++}`}>{tok.slice(1, -1)}</code>)
    else nodes.push(<em key={`${keyBase}-${k++}`}>{tok.slice(1, -1)}</em>)
    last = m.index + tok.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

/** 整段 markdown：段落 / 列表 / [来源N] 角标 → React 节点 */
function mdToNodes(answer: string, onJump: (n: number) => void): ReactNode[] {
  const parts = answer.split(/\[来源(\d+)\]/g)
  const out: ReactNode[] = []
  let blockKey = 0
  parts.forEach((p, i) => {
    if (i % 2 === 1) {
      const n = Number(p)
      out.push(<sup key={`src-${i}`} className="src-ref" onClick={() => onJump(n)}>[{n}]</sup>)
      return
    }
    if (!p) return
    const lines = p.split('\n')
    let list: string[] = []
    const flushList = () => {
      if (!list.length) return
      out.push(
        <ul key={`ul-${blockKey++}`}>
          {list.map((item, li) => (
            <li key={li}>{inlineToNodes(item, `li-${li}`)}</li>
          ))}
        </ul>,
      )
      list = []
    }
    lines.forEach((ln, li) => {
      const t = ln.trim()
      if (/^[-*•]\s+/.test(t)) { list.push(t.replace(/^[-*•]\s+/, '')); return }
      flushList()
      if (!t) return
      out.push(<p key={`p-${blockKey++}`}>{inlineToNodes(ln, `p-${li}`)}</p>)
    })
    flushList()
  })
  return out
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
export default function AskResult({ data, onPickName }: Props) {
  if (!data.ok) return null
  const intent = data.intent || '未知'
  const structured = data.route_used === 'structured'

  const jumpToSource = (n: number) => {
    const chips = document.querySelectorAll<HTMLElement>('.ask-src-chip')
    const target = chips[n - 1]
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target.style.boxShadow = '0 0 0 3px rgba(79,70,229,.25)'
    }
  }

  return (
    <div>
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
          {data.answer ? (
            data.rejected
              ? <div className="ask-answer ask-rejected">{data.answer}</div>
              : <div className="ask-answer">{mdToNodes(data.answer, jumpToSource)}</div>
          ) : (
            <div className="ask-answer ask-rejected">知识库检索完成，但回答生成暂不可用（未配置 LLM 或调用失败）。</div>
          )}

          {data.sources && data.sources.length ? (
            <div className="ask-sources">
              <div className="ask-src-title">依据来源（点击查看）</div>
              {data.sources.map((s, i) => (
                <span key={`${s.name}-${i}`} className="ask-src-chip" onClick={() => onPickName(s.name)}>
                  <span className="rn">[{i + 1}]</span>{s.name}
                </span>
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
    </div>
  )
}
