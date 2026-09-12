import { useEffect, useState } from 'react'

/** Indeterminate transport feedback: elapsed time is not a completion estimate. */
export default function RetrievalStatus({ active, phase, identity }: { active: boolean; phase?: string; identity: string }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    setElapsed(0)
    if (!active) return
    const started = performance.now()
    const timer = window.setInterval(() => setElapsed(Math.floor((performance.now() - started) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [active, identity])
  if (!active) return null
  return <div className="retrieval-telemetry" aria-busy="true">
    <div className="retrieval-heading"><span className="retrieval-beacon" aria-hidden="true" /><strong role="status">{phase || '请求已提交 · 等待服务响应'}</strong><time aria-label={`已等待 ${elapsed} 秒`}>{String(elapsed).padStart(2, '0')}s</time></div>
    <div className="retrieval-track" role="progressbar" aria-label="请求处理中，完成时间未知"><i /></div>
    <small>{elapsed >= 10 ? '请求尚未完成，你可以继续等待或停止生成。' : '收到内容后，档案将自动展开。'}</small>
  </div>
}
