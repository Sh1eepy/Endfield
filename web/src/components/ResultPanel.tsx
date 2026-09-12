import { useRef } from 'react'
import type { ReactNode, RefObject } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import type { LoadResult, Mode, ResultState } from '../App'
import type { RefItem, SynthesisData } from '../types'
import { mediaSrc } from '../utils'
import AskResult from './AskResult'
import DeviceCards from './DeviceCards'
import EmptyState from './EmptyState'
import KbCard from './KbCard'
import SynTree, { type SynTreeHandle } from './SynTree'

interface Props {
  mode: Mode
  title: string
  state: ResultState
  errorMsg: string
  result: LoadResult | null
  onPickName: (name: string) => void
  onRunQuery: (query: string) => void
  showTip: (x: number, y: number, content: ReactNode) => void
  hideTip: () => void
  synTreeRef: RefObject<HTMLDivElement>
  onStopAsk: () => void
}

/** 结果区顶部：封面图 + 相关引用（点击切换合成树） */
function ItemHead({ d, onPickName }: { d: SynthesisData; onPickName: (n: string) => void }) {
  if (!d.ok) return null
  // 干员详情自带 hero，不再叠加头卡
  const skip = Boolean(d.no_recipe && d.kb?.operator_detail)
  if (skip) return null
  const hasCover = Boolean(d.cover)
  const refs: RefItem[] = d.refs || []
  if (!hasCover && !refs.length) return null

  const tag = d.no_recipe
    ? '无流水线配方 · 知识库条目'
    : (d.tree && d.tree.kind === 'device' ? '设备 · 配方卡片' : '配方合成树')

  return (
    <>
      {hasCover ? (
        <div className="item-head">
          <img
            src={mediaSrc(d.cover)}
            alt=""
            className="item-cover"
            referrerPolicy="no-referrer"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
          <div>
            <div className="item-head-name">{d.item}</div>
            <div className="item-head-tag">{tag}</div>
          </div>
        </div>
      ) : null}
      {refs.length ? (
        <div className="refs-block">
          <div className="refs-title">相关引用（点击切换合成树）</div>
          <div className="refs-list">
            {refs.map((r, i) => (
              <span key={i} className="ref-chip" onClick={() => onPickName(r.name)}>
                {r.name}
                {r.count ? <span className="cnt">×{r.count}</span> : null}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </>
  )
}

function SynContent({ result, onPickName, showTip, hideTip, treeHandleRef }: {
  result: Extract<LoadResult, { kind: 'syn' }>
  onPickName: (n: string) => void
  showTip: (x: number, y: number, content: ReactNode) => void
  hideTip: () => void
  treeHandleRef: RefObject<SynTreeHandle>
}) {
  const d = result.data
  if (!d.ok) return null

  if (d.ambiguous) {
    return (
      <div style={{ color: 'var(--sub)', margin: '8px 0' }}>
        「{result.query}」匹配多个物品，请选择：
        {(d.candidates || []).map((n) => (
          <span
            key={n}
            className="sug-item"
            style={{ display: 'inline-block', margin: 4, padding: '6px 12px', border: '1px solid var(--border2)', borderRadius: 6, background: 'var(--panel2)', cursor: 'pointer' }}
            onClick={() => onPickName(n)}
          >
            {n}
          </span>
        ))}
      </div>
    )
  }

  const isDevice = d.tree?.kind === 'device'
  return (
    <>
      <ItemHead d={d} onPickName={onPickName} />
      {d.no_recipe && d.kb ? (
        <KbCard kb={d.kb} onPickName={onPickName} />
      ) : d.tree ? (
        isDevice
          ? <DeviceCards tree={d.tree} />
          : (
            <SynTree
              key={result.query}
              tree={d.tree}
              onPickName={onPickName}
              showTip={showTip}
              hideTip={hideTip}
              ref={treeHandleRef}
            />
          )
      ) : null}
    </>
  )
}

/** 结果面板：标题 + 树工具条 + 内容分发 */
export default function ResultPanel({
  mode, title, state, errorMsg, result, onPickName, onRunQuery, showTip, hideTip, synTreeRef,
  onStopAsk,
}: Props) {
  const treeHandleRef = useRef<SynTreeHandle>(null)
  const reducedMotion = useReducedMotion()

  const isTree = state === 'ready'
    && result?.kind === 'syn'
    && result.data.ok
    && !result.data.ambiguous
    && !result.data.no_recipe
    && result.data.tree?.kind !== 'device'
  const isStreaming = state === 'ready' && result?.kind === 'ask' && !!result.data.streaming

  return (
    <div className="panel">
      <div className="panel-head">
        <span>
          <i className="panel-kicker">OUTPUT</i>
          <b id="tree-title">{title}</b>
        </span>
        <div className="tree-toolbar" id="tree-toolbar">
          {isStreaming ? (
            <button className="tool-btn" type="button" onClick={onStopAsk}>停止生成</button>
          ) : null}
          {mode === 'syn' && <>
          <button className="tool-btn" title="收起所有分支" disabled={!isTree} onClick={() => treeHandleRef.current?.collapse()}>收起</button>
          <button className="tool-btn" title="展开所有分支" disabled={!isTree} onClick={() => treeHandleRef.current?.expand()}>展开</button>
          <button className="tool-btn" title="缩小" disabled={!isTree} onClick={() => treeHandleRef.current?.zoom(-0.1)}>−</button>
          <button className="tool-btn" title="重置缩放" disabled={!isTree} onClick={() => treeHandleRef.current?.reset()}>100%</button>
          <button className="tool-btn" title="放大" disabled={!isTree} onClick={() => treeHandleRef.current?.zoom(0.1)}>＋</button>
          </>}
        </div>
        <span className="panel-guide" style={{ fontSize: 12, color: 'var(--faint)' }}>{mode === 'syn' ? '圆点展开/收起 · 点击物品名跳转 · 叶子 = 基础资源' : '基于检索证据回答 · 点击来源核对'}</span>
      </div>
      <div id="syn-tree" ref={synTreeRef}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={mode}
            initial={reducedMotion ? false : { opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: reducedMotion ? 0 : -16 }}
            transition={{ duration: reducedMotion ? 0 : 0.3, ease: [0.2, 0, 0.1, 1] }}
          >
            {state === 'empty' ? (
              <EmptyState mode={mode} onDemo={onRunQuery} />
            ) : state === 'loading' ? (
              <div id="syn-empty">{mode === 'ask' ? '思考中…（检索 + AI 生成）' : '加载中…'}</div>
            ) : state === 'error' ? (
              <div className="msg bot"><span style={{ color: 'var(--danger)' }}>{errorMsg}</span></div>
            ) : result?.kind === 'syn' ? (
              <SynContent
                result={result}
                onPickName={onPickName}
                showTip={showTip}
                hideTip={hideTip}
                treeHandleRef={treeHandleRef}
              />
            ) : (
              result && <AskResult data={result.data} query={result.query} onPickName={onPickName} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
