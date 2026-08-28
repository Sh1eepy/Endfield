import type { Mode } from '../App'

interface Props {
  mode: Mode
  onDemo: (query: string, mode: Mode) => void
}

const DEMOS: Record<Mode, string[]> = {
  syn: ['重息壤', '碳块', '工业爆炸物'],
  ask: ['佩丽卡怎么玩', '解锁武陵需要什么条件', '主线任务有哪些'],
}

export default function EmptyState({ mode, onDemo }: Props) {
  const ask = mode === 'ask'
  const demos = DEMOS[mode]
  return (
    <div className="empty-console">
      <div className="empty-code">{ask ? 'KNOWLEDGE QUERY / READY' : 'SYNTHESIS QUERY / READY'}</div>
      <h2>{ask ? '你想了解什么？' : '选择一个目标物品'}</h2>
      <p>
        {ask
          ? '可以询问角色、任务、材料数值、地区解锁或两个物品之间的区别。'
          : '系统会从目标物品开始，纵向展开设备、原料，直到基础资源。'}
      </p>
      <div className="demo-list">
        {demos.map((q) => (
          <button key={q} className="demo-btn" onClick={() => onDemo(q, mode)}>{q}</button>
        ))}
      </div>
    </div>
  )
}
