import { useEffect, useState } from 'react'
import { backupApi } from '@/services/api/client'
import type { BackupDrillOut, BackupOut, BackupVerifyOut } from '@/types/api'
import styles from './BackupPage.module.css'

export function BackupPage() {
  const [backups, setBackups] = useState<BackupOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [creating, setCreating] = useState(false)
  const [actionResult, setActionResult] = useState<string | null>(null)
  const [drillResult, setDrillResult] = useState<BackupDrillOut | null>(null)
  const [verifyResult, setVerifyResult] = useState<BackupVerifyOut | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await backupApi.list()
      setBackups(data.backups)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load backups')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const handleCreate = async () => {
    setCreating(true)
    setError(null)
    setActionResult(null)
    try {
      const b = await backupApi.create(notes)
      setBackups((prev) => [b, ...prev])
      setNotes('')
      setActionResult(`Backup created: ${b.backup_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Create failed')
    } finally {
      setCreating(false)
    }
  }

  const handleVerify = async (id: string) => {
    setActionResult(null)
    setDrillResult(null)
    setVerifyResult(null)
    try {
      setVerifyResult(await backupApi.verify(id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Verify failed')
    }
  }

  const handleDrill = async (id: string) => {
    setActionResult(null)
    setVerifyResult(null)
    setDrillResult(null)
    try {
      setDrillResult(await backupApi.drill(id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Drill failed')
    }
  }

  const handleRestore = async (id: string) => {
    if (!window.confirm(`Restore backup ${id}? The live database will be overwritten. Restart JARVIS after.`)) return
    try {
      const r = await backupApi.restore(id)
      setActionResult(r.message)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Restore failed')
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm(`Delete backup ${id}?`)) return
    try {
      await backupApi.delete(id)
      setBackups((prev) => prev.filter((b) => b.backup_id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>BACKUP & RECOVERY</h1>
        <span className={styles.count}>{backups.length} backups</span>
      </header>

      <div className={styles.createRow}>
        <input
          className={styles.notesInput}
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        <button className={styles.createBtn} onClick={handleCreate} disabled={creating}>
          {creating ? 'Creating…' : '+ Create Backup'}
        </button>
      </div>

      {error && <p className={styles.error} role="alert">{error}</p>}
      {actionResult && <p className={styles.success}>{actionResult}</p>}

      {verifyResult && (
        <div className={`${styles.resultBox} ${verifyResult.ok ? styles.ok : styles.fail}`}>
          <strong>Verify {verifyResult.backup_id.slice(0, 12)}…</strong>
          <span>{verifyResult.ok ? '✓ OK' : '✗ FAIL'}</span>
          <span className={styles.mono}>{verifyResult.message}</span>
        </div>
      )}

      {drillResult && (
        <div className={`${styles.resultBox} ${drillResult.passed ? styles.ok : styles.fail}`}>
          <strong>Drill {drillResult.backup_id.slice(0, 12)}… — {drillResult.passed ? '✓ PASSED' : '✗ FAILED'}</strong>
          <p className={styles.summary}>{drillResult.summary}</p>
          <ul className={styles.checkList}>
            {drillResult.checks.map((c) => (
              <li key={c.name} className={c.passed ? styles.checkOk : styles.checkFail}>
                {c.passed ? '✓' : '✗'} {c.name}: {c.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : backups.length === 0 ? (
        <p className={styles.empty}>No backups yet. Create one above.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Created</th>
              <th>Version</th>
              <th>Notes</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {backups.map((b) => (
              <tr key={b.backup_id}>
                <td className={styles.mono}>{b.backup_id.slice(0, 12)}…</td>
                <td className={styles.mono}>{new Date(b.created_at).toLocaleString()}</td>
                <td className={styles.mono}>{b.app_version}</td>
                <td>{b.notes || '—'}</td>
                <td className={styles.actions}>
                  <button onClick={() => void handleVerify(b.backup_id)}>Verify</button>
                  <button onClick={() => void handleDrill(b.backup_id)}>Drill</button>
                  <button className={styles.restoreBtn} onClick={() => void handleRestore(b.backup_id)}>Restore</button>
                  <button className={styles.deleteBtn} onClick={() => void handleDelete(b.backup_id)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
