import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { auditApi, healthApi } from '@/services/api/client'
import styles from './ObservabilityPage.module.css'

function statusColor(status: string) {
  if (status === 'healthy' || status === 'READY') return 'var(--hud-success)'
  if (status === 'degraded' || status === 'DEGRADED') return 'var(--hud-warning)'
  if (status === 'not_configured') return 'var(--hud-text-secondary)'
  return 'var(--hud-danger)'
}

function decisionColor(d: string) {
  if (d === 'ALLOW') return 'var(--hud-success)'
  if (d === 'REQUIRES_CONFIRMATION') return 'var(--hud-warning)'
  return 'var(--hud-danger)'
}

function HealthPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['health-deps'],
    queryFn: () => healthApi.dependencies(),
    refetchInterval: 15_000,
  })
  return (
    <section className={styles.panel}>
      <h2 className={styles.panelTitle}>System Health</h2>
      {isLoading && <div className={styles.loading}>Loading…</div>}
      {data && (
        <>
          <div className={styles.overallStatus} style={{ color: statusColor(data.jarvis) }}>
            ● {data.jarvis}
          </div>
          <table className={styles.table}>
            <thead><tr><th>Dependency</th><th>Status</th><th>Detail</th></tr></thead>
            <tbody>
              {data.dependencies.map((dep) => (
                <tr key={dep.name}>
                  <td className={styles.mono}>{dep.name}</td>
                  <td style={{ color: statusColor(dep.status) }}>{dep.status}</td>
                  <td className={styles.detail}>{dep.detail ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

function ToolMetricsPanel() {
  const { data } = useQuery({
    queryKey: ['audit-metrics'],
    queryFn: () => auditApi.list({ limit: 200 }),
    refetchInterval: 30_000,
  })
  if (!data) return null

  const items = data.items
  const total = items.length
  const succeeded = items.filter((i) => i.success).length
  const avgDuration = total > 0
    ? Math.round(items.reduce((s, i) => s + i.duration_ms, 0) / total)
    : 0

  const counts: Record<string, number> = {}
  for (const item of items) counts[item.tool_name] = (counts[item.tool_name] ?? 0) + 1
  const topTools = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8)
  const maxCount = topTools[0]?.[1] ?? 1

  return (
    <section className={styles.panel}>
      <h2 className={styles.panelTitle}>Tool Metrics (last 200)</h2>
      <div className={styles.metricRow}>
        <div className={styles.metric}>
          <span className={styles.metricValue}>{total}</span>
          <span className={styles.metricLabel}>Total</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricValue} style={{ color: 'var(--hud-success)' }}>{succeeded}</span>
          <span className={styles.metricLabel}>OK</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricValue} style={{ color: 'var(--hud-danger)' }}>{total - succeeded}</span>
          <span className={styles.metricLabel}>Failed</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricValue}>{avgDuration}ms</span>
          <span className={styles.metricLabel}>Avg</span>
        </div>
      </div>
      <div className={styles.barChart}>
        {topTools.map(([name, count]) => (
          <div key={name} className={styles.barRow}>
            <span className={`${styles.mono} ${styles.barLabel}`}>{name}</span>
            <div className={styles.barTrack}>
              <div className={styles.barFill} style={{ width: `${Math.round((count / maxCount) * 100)}%` }} />
            </div>
            <span className={styles.barCount}>{count}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function AuditTimeline() {
  const [page, setPage] = useState(0)
  const limit = 20
  const { data, isLoading } = useQuery({
    queryKey: ['obs-audit', page],
    queryFn: () => auditApi.list({ limit, offset: page * limit }),
  })
  return (
    <section className={styles.panel}>
      <h2 className={styles.panelTitle}>Recent Tool Executions</h2>
      {isLoading && <div className={styles.loading}>Loading…</div>}
      {data && (
        <>
          <table className={styles.table}>
            <thead>
              <tr><th>Time</th><th>Tool</th><th>Risk</th><th>Decision</th><th>ms</th><th>Result</th></tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.id}>
                  <td className={styles.mono}>{new Date(item.created_at).toLocaleTimeString()}</td>
                  <td className={styles.mono}>{item.tool_name}</td>
                  <td className={styles.mono}>{item.risk_level}</td>
                  <td style={{ color: decisionColor(item.policy_decision) }}>{item.policy_decision}</td>
                  <td className={styles.mono}>{item.duration_ms}</td>
                  <td style={{ color: item.success ? 'var(--hud-success)' : 'var(--hud-danger)' }}>
                    {item.success ? '✓' : '✗'}
                    {item.error && <span title={item.error}> ⚠</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className={styles.pagination}>
            <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>← Prev</button>
            <span>Page {page + 1}</span>
            <button onClick={() => setPage((p) => p + 1)} disabled={data.items.length < limit}>Next →</button>
          </div>
        </>
      )}
    </section>
  )
}

export function ObservabilityPage() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>OBSERVABILITY</span>
        <span className={styles.subtitle}>Health · Metrics · Traces</span>
      </div>
      <div className={styles.grid}>
        <HealthPanel />
        <ToolMetricsPanel />
      </div>
      <AuditTimeline />
    </div>
  )
}
