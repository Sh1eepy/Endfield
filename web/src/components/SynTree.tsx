import { forwardRef, useCallback, useId, useImperativeHandle, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import type { SynTree as SynTreeApi, SynTreeChild } from '../types'

interface Props {
  tree: SynTreeApi
  onPickName: (name: string) => void
  showTip: (x: number, y: number, content: ReactNode) => void
  hideTip: () => void
}

export interface SynTreeHandle {
  collapse: () => void
  expand: () => void
  zoom: (delta: number) => void
  reset: () => void
}

interface TreeNode {
  name: string
  item_id?: string
  kind: 'item' | 'recipe'
  duration?: number
  count?: number
  leaf?: boolean
  truncated?: boolean
  cover?: string
  key: string
  _hasChildren?: boolean
  children: TreeNode[]
}

interface LayoutNode extends TreeNode {
  x: number
  y: number
  children: LayoutNode[]
}

// 纵向布局常量（与原 d3.tree().nodeSize([116, 148]) 等价）
const X_UNIT = 116
const Y_STEP = 148

/** 后端树 → 内部树（等价旧版 synToD3） */
function synToTree(node: SynTreeApi | SynTreeChild, key = 'root'): TreeNode {
  const d: TreeNode = {
    name: node.name,
    item_id: node.item_id,
    kind: 'item',
    leaf: node.leaf,
    truncated: node.truncated,
    cover: node.cover,
    key,
    children: [],
  }
  ;(node.recipes || []).forEach((r, ri) => {
    const recipeKey = `${key}/r${ri}`
    const rn: TreeNode = {
      name: r.machine,
      kind: 'recipe',
      duration: r.duration,
      cover: r.cover,
      key: recipeKey,
      children: [],
    }
    ;(r.inputs || []).forEach((x, xi) => {
      const cn = synToTree(x, `${recipeKey}/i${xi}:${x.item_id || x.name}`)
      cn.count = x.count
      rn.children.push(cn)
    })
    d.children.push(rn)
  })
  return d
}

/** 折叠过滤（等价旧版 visible） */
function applyCollapsed(node: TreeNode, collapsed: Set<string>): TreeNode {
  const copy: TreeNode = { ...node }
  copy._hasChildren = Boolean(node.children && node.children.length)
  copy.children = collapsed.has(node.key)
    ? []
    : (node.children || []).map((c) => applyCollapsed(c, collapsed))
  return copy
}

/** tidy 布局：叶子占 1 单位宽，内部节点取子节点区间中点（等价 d3.tree 叶子对齐布局）。
 * 内部全程用单位坐标，最后统一换算成像素，避免单位/像素混用导致坐标指数爆炸。 */
function buildLayout(source: TreeNode): LayoutNode {
  const widthOf = (n: TreeNode): number =>
    n.children.length ? n.children.reduce((s, c) => s + widthOf(c), 0) : 1

  const placeNode = (n: TreeNode, x0: number, depth: number): LayoutNode => {
    let cursor = x0
    const children: LayoutNode[] = []
    for (const c of n.children) {
      const w = widthOf(c)
      children.push(placeNode(c, cursor, depth + 1))
      cursor += w
    }
    const x = children.length
      ? (children[0].x + children[children.length - 1].x) / 2
      : x0 + 0.5
    return { ...n, x, y: depth, children }
  }
  const unitLayout = placeNode(source, 0, 0)
  const toPx = (n: LayoutNode): LayoutNode => ({
    ...n,
    x: n.x * X_UNIT,
    y: n.y * Y_STEP,
    children: n.children.map(toPx),
  })
  return toPx(unitLayout)
}

/** 配方树：纯 React 递归 SVG，不依赖 d3。 */
const SynTree = forwardRef<SynTreeHandle, Props>(function SynTree(
  { tree, onPickName, showTip, hideTip }: Props,
  ref,
) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [scale, setScale] = useState(1)
  const [failedCovers, setFailedCovers] = useState<Set<string>>(new Set())
  // useId 输出含冒号，URL(#id) 无法匹配，需要去冒号
  const uid = useId().replace(/:/g, '')

  const source = useMemo(() => synToTree(tree), [tree])
  const visibleTree = useMemo(() => applyCollapsed(source, collapsed), [source, collapsed])
  const layout = useMemo(() => buildLayout(visibleTree), [visibleTree])

  const nodes: LayoutNode[] = useMemo(() => {
    const out: LayoutNode[] = []
    const walk = (n: LayoutNode) => { out.push(n); n.children.forEach(walk) }
    walk(layout)
    return out
  }, [layout])

  const links: { sx: number; sy: number; tx: number; ty: number; count?: number; fromItem: boolean }[] =
    useMemo(() => {
      const out: { sx: number; sy: number; tx: number; ty: number; count?: number; fromItem: boolean }[] = []
      const walk = (n: LayoutNode) => {
        n.children.forEach((c) => {
          out.push({ sx: n.x, sy: n.y, tx: c.x, ty: c.y, count: c.count, fromItem: n.kind === 'item' })
          walk(c)
        })
      }
      walk(layout)
      return out
    }, [layout])

  const totalUnits = useMemo(() => {
    let max = 0
    const walk = (n: LayoutNode) => { max = Math.max(max, n.x / X_UNIT + 1); n.children.forEach(walk) }
    walk(layout)
    return max
  }, [layout])
  const maxDepth = useMemo(() => {
    let max = 0
    const walk = (n: LayoutNode) => { max = Math.max(max, n.y / Y_STEP); n.children.forEach(walk) }
    walk(layout)
    return max
  }, [layout])

  const minX = useMemo(() => Math.min(...nodes.map((n) => n.x)), [nodes])
  const W = Math.max(920, totalUnits * X_UNIT + 190)
  const H = Math.max(540, (maxDepth + 1) * Y_STEP + 190)

  const toggle = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
    hideTip()
  }, [hideTip])

  useImperativeHandle(ref, () => ({
    collapse() { setCollapsed(new Set([source.key])) },
    expand() { setCollapsed(new Set()) },
    zoom(delta: number) { setScale((s) => Math.max(0.7, Math.min(1.35, s + delta))) },
    reset() { setScale(1) },
  }), [source.key])

  const cardPath = (w: number) =>
    `M${-w / 2},-44 H${w / 2 - 12} L${w / 2},-32 V44 H${-w / 2 + 12} L${-w / 2},32 Z`

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: `${W * scale}px`, height: `${H * scale}px` }}
      aria-label={`${tree.name}纵向配方树`}
    >
      <g transform={`translate(${85 - minX},62)`}>
        {links.map((l, i) => (
          <path
            key={`link-${i}`}
            className={l.fromItem ? 'link cnt' : 'link'}
            d={`M${l.sx},${l.sy}C${l.sx},${(l.sy + l.ty) / 2} ${l.tx},${(l.sy + l.ty) / 2} ${l.tx},${l.ty}`}
          />
        ))}
        {links.filter((l) => l.count).map((l, i) => (
          <text
            key={`el-${i}`}
            className="edge-label"
            textAnchor="middle"
            x={(l.sx + l.tx) / 2 + 13}
            y={(l.sy + l.ty) / 2 - 5}
          >
            ×{l.count}
          </text>
        ))}
        {nodes.map((d, i) => {
          const isMachine = d.kind === 'recipe'
          const w = isMachine ? 104 : 92
          const clipId = `${uid}-clip-${i}`
          return (
            <motion.g
              key={d.key}
              className={`node node-card ${isMachine ? 'node-recipe' : 'node-item'}`}
              style={{ x: d.x, y: d.y, transformBox: 'fill-box', transformOrigin: 'center' }}
              initial={{ opacity: 0, scale: 0.88 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: Math.min(0.018 * i, 0.55), duration: 0.22, ease: 'easeOut' }}
              onMouseOver={(ev) => {
                showTip(ev.clientX + 12, ev.clientY + 12, (
                  <div>
                    <div className="t-name">{d.name}</div>
                    {d.duration ? <div className="t-row">设备耗时 {d.duration}s</div> : null}
                    {d.count ? <div className="t-row">需要 ×{d.count}</div> : null}
                    {d.truncated ? <div className="t-row">…已截断</div> : null}
                  </div>
                ))
              }}
              onMouseOut={hideTip}
            >
              <g
                className="node-toggle"
                onClick={(ev) => { ev.stopPropagation(); if (d._hasChildren) toggle(d.key) }}
              >
                <path className="node-card-bg" d={cardPath(w)} />
                {d.cover && !failedCovers.has(d.key) ? (
                  <>
                    <clipPath id={clipId}>
                      <rect x={-w / 2 + 7} y={-37} width={w - 14} height={56} rx={3} />
                    </clipPath>
                    <image
                      className="node-card-image"
                      href={d.cover}
                      x={-w / 2 + 7}
                      y={-37}
                      width={w - 14}
                      height={56}
                      preserveAspectRatio="xMidYMid meet"
                      clipPath={`url(#${clipId})`}
                      onError={() => setFailedCovers((prev) => new Set(prev).add(d.key))}
                    />
                  </>
                ) : (
                  <text className="node-card-fallback" textAnchor="middle" y={-5}>
                    {isMachine ? 'MACHINE' : 'ITEM'}
                  </text>
                )}
              </g>
              <text
                className="node-card-label"
                textAnchor="middle"
                y={57}
                onClick={(ev) => { ev.stopPropagation(); if (!isMachine) onPickName(d.name) }}
              >
                {d.name.length > 8 ? `${d.name.slice(0, 8)}…` : d.name}
              </text>
              <text className="node-card-sub" textAnchor="middle" y={70}>
                {isMachine ? `${d.duration || 0}s // DEVICE` : (d.leaf ? 'BASE RESOURCE' : 'ITEM NODE')}
              </text>
              {d._hasChildren && (
                <text className="collapse-mark" x={w / 2 - 8} y={-31} textAnchor="middle">
                  {collapsed.has(d.key) ? '+' : '−'}
                </text>
              )}
            </motion.g>
          )
        })}
      </g>
    </svg>
  )
})

export default SynTree
