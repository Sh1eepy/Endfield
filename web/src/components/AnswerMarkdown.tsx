import type { ReactNode } from 'react'

/** 只生成 React 节点，不解释模型输出的 HTML；引用在块内解析，不切断表格/列表。 */
function inline(text: string, onJump: (n: number) => void): ReactNode[] {
  const out: ReactNode[] = []
  const tokens = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[来源\d+\]|\\[\\|*`])/g
  let last = 0
  for (const match of text.matchAll(tokens)) {
    const i = match.index!
    if (i > last) out.push(text.slice(last, i))
    const token = match[0]
    if (token.startsWith('`')) out.push(<code key={i}>{token.slice(1, -1)}</code>)
    else if (token.startsWith('**')) out.push(<strong key={i}>{inline(token.slice(2, -2), onJump)}</strong>)
    else if (token.startsWith('*')) out.push(<em key={i}>{inline(token.slice(1, -1), onJump)}</em>)
    else if (token.startsWith('\\')) out.push(token.slice(1))
    else {
      const n = Number(token.slice(3, -1))
      out.push(<sup key={i} className="src-ref">
        <button type="button" aria-label={`查看来源${n}`} onClick={() => onJump(n)}>[{n}]</button>
      </sup>)
    }
    last = i + token.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function cells(line: string): string[] {
  const parts: string[] = []
  let part = ''
  let code = false
  for (let i = 0; i < line.length; i++) {
    const char = line[i]
    if (char === '\\' && i + 1 < line.length) { part += char + line[++i]; continue }
    if (char === '`') code = !code
    if (char === '|' && !code) { parts.push(part.trim()); part = '' }
    else part += char
  }
  parts.push(part.trim())
  if (parts[0] === '') parts.shift()
  if (parts[parts.length - 1] === '') parts.pop()
  return parts
}

export default function AnswerMarkdown({ answer, onJump }: {
  answer: string
  onJump: (n: number) => void
}) {
  const lines = answer.replace(/\r\n?/g, '\n').split('\n')
  const out: ReactNode[] = []
  for (let i = 0; i < lines.length;) {
    const key = i
    const line = lines[i].trim()
    if (!line) { i++; continue }
    // 代码块中的引用和 HTML 都保留字面内容。
    if (line.startsWith('```')) {
      const code: string[] = []
      for (i++; i < lines.length && !lines[i].trim().startsWith('```'); i++) code.push(lines[i])
      i++
      out.push(<pre key={key}><code>{code.join('\n')}</code></pre>)
      continue
    }
    const header = cells(line)
    const separators = cells(lines[i + 1] || '')
    if (line.includes('|') && header.length > 0 && separators.length === header.length
      && separators.every((s) => /^:?-{3,}:?$/.test(s))) {
      const alignment = separators.map((s): 'left' | 'center' | 'right' =>
        s.endsWith(':') ? (s.startsWith(':') ? 'center' : 'right') : 'left')
      const rows: string[][] = []
      for (i += 2; i < lines.length && lines[i].trim() && lines[i].includes('|'); i++) rows.push(cells(lines[i]))
      out.push(<div className="ask-table-scroll" key={key}>
        <table>
          <thead><tr>{header.map((cell, c) => <th key={c} scope="col" style={{ textAlign: alignment[c] }}>{inline(cell, onJump)}</th>)}</tr></thead>
          <tbody>{rows.map((row, r) => <tr key={r}>{header.map((_, c) =>
            <td key={c} style={{ textAlign: alignment[c] }}>{inline(row[c] || '', onJump)}</td>)}</tr>)}</tbody>
        </table>
      </div>)
      continue
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line)
    if (heading) {
      const Tag = `h${heading[1].length}` as 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'
      out.push(<Tag key={key}>{inline(heading[2], onJump)}</Tag>)
      i++
      continue
    }
    const listPattern = /^(?:[-*•]\s+|\d+[.)]\s+)/
    if (listPattern.test(line)) {
      const ordered = /^\d/.test(line)
      const items: ReactNode[] = []
      const start = ordered ? Number.parseInt(line, 10) : undefined
      while (i < lines.length && listPattern.test(lines[i].trim()) && /^\d/.test(lines[i].trim()) === ordered) {
        items.push(<li key={i}>{inline(lines[i].trim().replace(listPattern, ''), onJump)}</li>)
        i++
      }
      out.push(ordered ? <ol key={key} start={start}>{items}</ol> : <ul key={key}>{items}</ul>)
      continue
    }
    out.push(<p key={key}>{inline(lines[i], onJump)}</p>)
    i++
  }
  return <>{out}</>
}
