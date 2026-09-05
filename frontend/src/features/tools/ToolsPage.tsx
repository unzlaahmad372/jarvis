import { useEffect, useState } from 'react'
import { toolsApi } from '@/services/api/client'
import type { ConfirmationOut, ToolExecuteResponse, ToolExecutionOut, ToolOut } from '@/types/api'
import styles from './ToolsPage.module.css'

const RISK_COLORS: Record<string, string> = {
  READ_ONLY: 'var(--hud-success)',
  LOW_RISK: 'var(--hud-info)',
  SENSITIVE: 'var(--hud-warning)',
  DANGEROUS: 'var(--hud-danger)',
}

export function ToolsPage() {
  const [tools, setTools] = useState<ToolOut[]>([])
  const [audit, setAudit] = useState<ToolExecutionOut[]>([])
  const [selected, setSelected] = useState<ToolOut | null>(null)
  const [params, setParams] = useState('{}')
  const [result, setResult] = useState<ToolExecuteResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingConfirm, setPendingConfirm] = useState<ConfirmationOut | null>(null)

  useEffect(() => {
    toolsApi.list().then(setTools).catch(() => setError('Failed to load tools'))
    toolsApi.audit().then(setAudit).catch(() => {})
  }, [])

  const handleExecute = async () => {
    if (!selected) return
    setRunning(true)
    setResult(null)
    setError(null)
    try {
      let parsed: Record<string, unknown> = {}
      try { parsed = JSON.parse(params) } catch { setError('Invalid JSON parameters'); setRunning(false); return }
      const res = await toolsApi.execute(selected.name, { parameters: parsed })
      setResult(res)
      if (res.requires_confirmation && res.policy_decision === 'REQUIRES_CONFIRMATION') {
        // Fetch the pending confirmation so we can show the approval panel
        // The planner creates it; for direct tool execution we show the inline note
        setPendingConfirm(null)
      }
      const fresh = await toolsApi.audit()
      setAudit(fresh)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Execution failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>TOOLS</h1>
        <span className={styles.count}>{tools.length} registered</span>
      </header>

      <div className={styles.layout}>
        {/* Tool list */}
        <section className={styles.toolList} aria-label="Available tools">
          {tools.map((t) => (
            <button
              key={t.name}
              className={`${styles.toolCard} ${selected?.name === t.name ? styles.toolCardActive : ''}`}
              onClick={() => { setSelected(t); setParams('{}'); setResult(null) }}
            >
              <div className={styles.toolName}>{t.name}</div>
              <span
                className={styles.riskBadge}
                style={{ color: RISK_COLORS[t.risk_level] ?? 'var(--hud-text-secondary)' }}
              >
                {t.risk_level}
              </span>
              <p className={styles.toolDesc}>{t.description}</p>
            </button>
          ))}
        </section>

        {/* Execution panel */}
        <section className={styles.execPanel}>
          {selected ? (
            <>
              <h2 className={styles.execTitle}>{selected.name}</h2>
              <p className={styles.execDesc}>{selected.description}</p>
              <label className={styles.paramLabel}>
                Parameters (JSON)
                <textarea
                  className={styles.paramInput}
                  value={params}
                  onChange={(e) => setParams(e.target.value)}
                  rows={4}
                  spellCheck={false}
                />
              </label>
              <button
                className={styles.runBtn}
                onClick={handleExecute}
                disabled={running}
              >
                {running ? 'Running…' : 'Execute'}
              </button>

              {error && <p className={styles.error} role="alert">{error}</p>}

              {result && (
                <div className={styles.result}>
                  <div className={styles.resultHeader}>
                    <span className={result.success ? styles.ok : styles.fail}>
                      {result.success ? '✓ SUCCESS' : '✗ FAILED'}
                    </span>
                    <span className={styles.policyBadge}>{result.policy_decision}</span>
                  </div>
                  {result.requires_confirmation && (
                    <div className={styles.confirmNote}>
                      <p>⚠ This action requires confirmation before it can execute.</p>
                      <p className={styles.confirmHint}>
                        Use the chat interface to trigger this tool — JARVIS will present
                        an approval panel with the exact action digest.
                      </p>
                    </div>
                  )}
                  {result.error && <p className={styles.error}>{result.error}</p>}
                  {result.output && (
                    <pre className={styles.output}>{result.output}</pre>
                  )}
                  {result.truncated && (
                    <p className={styles.truncated}>Output truncated to size limit.</p>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className={styles.empty}>Select a tool to execute it.</p>
          )}
        </section>
      </div>

      {/* Audit log */}
      <section className={styles.auditSection}>
        <h2 className={styles.auditTitle}>AUDIT LOG</h2>
        {audit.length === 0 ? (
          <p className={styles.empty}>No executions yet.</p>
        ) : (
          <table className={styles.auditTable}>
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
              {audit.map((row) => (
                <tr key={row.id}>
                  <td className={styles.mono}>{row.tool_name}</td>
                  <td style={{ color: RISK_COLORS[row.risk_level] }}>{row.risk_level}</td>
                  <td className={styles.mono}>{row.policy_decision}</td>
                  <td className={row.success ? styles.ok : styles.fail}>
                    {row.success ? '✓' : '✗'}
                  </td>
                  <td className={styles.mono}>{row.duration_ms}ms</td>
                  <td className={styles.mono}>{new Date(row.created_at).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
