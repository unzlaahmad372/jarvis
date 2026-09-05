import { useEffect, useState } from 'react'
import { auditApi } from '@/services/api/client'
import type { AuditPageOut, RetentionResult, ToolExecutionOut } from '@/types/api'
import styles from './AuditPage.module.css'

const RISK_COLORS: Record<string, string> = {
  READ_ONLY: 'var(--hud-success)',
  LOW_RISK: 'var(--hud-info)',
  SENSITIVE: 'var(--hud-warning)',
  DANGEROUS: 'var(--hud-danger)',
}

const DECISIONS = ['', 'ALLOW', 'REQUIRES_CONFIRMATION', 'DENY']
const PAGE_SIZE = 50

export function AuditPage() {
  const [page, setPage] = useState<AuditPageOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toolFilter, setToolFilter] = useState('')
  const [decisionFilter, setDecisionFilter] = useState('')
  const [successFilter, setSuccessFilter] = useState<'' | 'true' | 'false'>('')
  const [offset, setOffset] = useState(0)
  const [retentionResult, setRetentionResult] = useState<RetentionResult | null>(null)
  const [runningRetention, setRunningRetention] = useState(false)

  const load = async (off = offset) => {
    setLoading(true)
    setError(null)
    try {
      const params: Parameters<typeof auditApi.list>[0] = { limit: PAGE_SIZE, offset: off }
      if (toolFilter) params.tool_name = toolFilter
      if (decisionFilter) params.policy_decision = decisionFilter
      if (successFilter !== '') params.success = successFilter === 'true'
      setPage(await auditApi.list(params))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load audit log')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load(0); setOffset(0) }, [toolFilter, decisionFilter, successFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleRunRetention = async () => {
    setRunningRetention(true)
    setRetentionResult(null)
    try {
      setRetentionResult(await auditApi.runRetention())
      void load(offset)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Retention run failed')
    } finally {
      setRunningRetention(false)
    }
  }

  const rows: ToolExecutionOut[] = page?.items ?? []
  const total = page?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  const goTo = (newOffset: number) => {
    setOffset(newOffset)
    void load(newOffset)
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>AUDIT LOG</h1>
        <span className={styles.count}>{total} records</span>
        <button
          className={styles.retentionBtn}
          onClick={handleRunRetention}
          disabled={runningRetention}
        >
          {runningRetention ? 'Running…' : 'Run Retention'}
        </button>
      </header>

      {retentionResult && (
        <div className={styles.retentionBox}>
          <span>Retention complete — {retentionResult.total_deleted} records purged</span>
          <span>conversations: {retentionResult.conversations_deleted}</span>
          <span>tool logs: {retentionResult.tool_executions_deleted}</span>
          <span>automation logs: {retentionResult.automation_executions_deleted}</span>
          {retentionResult.errors.length > 0 && (
            <span className={styles.retentionErrors}>Errors: {retentionResult.errors.join('; ')}</span>
          )}
        </div>
      )}

      <div className={styles.filters}>
        <input
          className={styles.filterInput}
          placeholder="Filter by tool name"
          value={toolFilter}
          onChange={(e) => setToolFilter(e.target.value)}
        />
        <select
          className={styles.filterSelect}
          value={decisionFilter}
          onChange={(e) => setDecisionFilter(e.target.value)}
        >
          {DECISIONS.map((d) => <option key={d} value={d}>{d || 'All decisions'}</option>)}
        </select>
        <select
          className={styles.filterSelect}
          value={successFilter}
          onChange={(e) => setSuccessFilter(e.target.value as '' | 'true' | 'false')}
        >
          <option value="">All results</option>
          <option value="true">Success</option>
          <option value="false">Failed</option>
        </select>
      </div>

      {error && <p className={styles.error} role="alert">{error}</p>}

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : rows.length === 0 ? (
        <p className={styles.empty}>No records match the current filters.</p>
      ) : (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Tool</th>
                <th>Risk</th>
                <th>Decision</th>
                <th>Result</th>
                <th>Duration</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className={styles.mono}>{row.tool_name}</td>
                  <td style={{ color: RISK_COLORS[row.risk_level] ?? 'var(--hud-text-secondary)' }}>
                    {row.risk_level}
                  </td>
                  <td className={styles.mono}>{row.policy_decision}</td>
                  <td className={row.success ? styles.ok : styles.fail}>
                    {row.success ? '✓' : '✗'}
                    {row.error && <span className={styles.errDetail} title={row.error}> ⓘ</span>}
                  </td>
                  <td className={styles.mono}>{row.duration_ms}ms</td>
                  <td className={styles.mono}>{new Date(row.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {totalPages > 1 && (
            <div className={styles.pagination}>
              <button disabled={offset === 0} onClick={() => goTo(offset - PAGE_SIZE)}>← Prev</button>
              <span>{currentPage} / {totalPages}</span>
              <button disabled={offset + PAGE_SIZE >= total} onClick={() => goTo(offset + PAGE_SIZE)}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
