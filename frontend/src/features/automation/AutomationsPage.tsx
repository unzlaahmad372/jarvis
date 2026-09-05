import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { automationApi } from '@/services/api/client'
import type { AutomationJobOut, AutomationJobCreate } from '@/types/api'
import styles from './AutomationsPage.module.css'

const STATUS_BADGE: Record<string, string> = {
  SUCCESS: styles.success,
  FAILED: styles.failed,
  RUNNING: styles.running,
  SKIPPED: styles.skipped,
  CANCELLED: styles.skipped,
  TIMEOUT: styles.failed,
  PARTIAL: styles.skipped,
}

const CEILING_LABELS: Record<string, string> = {
  READ_ONLY: 'Read-only',
  LOW_RISK: 'Low-risk',
}

const OVERLAP_LABELS: Record<string, string> = {
  SKIP: 'Skip',
  QUEUE: 'Queue',
  REPLACE: 'Replace',
  ALLOW: 'Allow',
}

function JobRow({
  job,
  onToggle,
  onTrigger,
  onDelete,
  onSelect,
  selected,
}: {
  job: AutomationJobOut
  onToggle: (id: number, enabled: boolean) => void
  onTrigger: (id: number) => void
  onDelete: (id: number) => void
  onSelect: (id: number) => void
  selected: boolean
}) {
  return (
    <tr
      className={`${styles.row} ${selected ? styles.selectedRow : ''}`}
      onClick={() => onSelect(job.id)}
    >
      <td className={styles.cell}>
        <span className={`${styles.dot} ${job.enabled ? styles.dotOn : styles.dotOff}`} />
        {job.name}
      </td>
      <td className={styles.cell}><code>{job.schedule}</code></td>
      <td className={styles.cell}>{CEILING_LABELS[job.permission_ceiling] ?? job.permission_ceiling}</td>
      <td className={styles.cell}>{OVERLAP_LABELS[job.overlap_policy] ?? job.overlap_policy}</td>
      <td className={styles.cell}>
        {job.last_run_at ? new Date(job.last_run_at).toLocaleString() : '—'}
      </td>
      <td className={styles.cell} onClick={(e) => e.stopPropagation()}>
        <button
          className={styles.btn}
          onClick={() => onToggle(job.id, !job.enabled)}
          title={job.enabled ? 'Disable' : 'Enable'}
        >
          {job.enabled ? 'Disable' : 'Enable'}
        </button>
        <button
          className={styles.btn}
          onClick={() => onTrigger(job.id)}
          disabled={!job.enabled}
          title="Trigger now"
        >
          ▶
        </button>
        <button
          className={`${styles.btn} ${styles.btnDanger}`}
          onClick={() => onDelete(job.id)}
          title="Delete job"
        >
          ✕
        </button>
      </td>
    </tr>
  )
}

const EMPTY_FORM: AutomationJobCreate = {
  name: '',
  schedule: '0 8 * * *',
  action_type: 'tool',
  action_payload: {},
  description: '',
  permission_ceiling: 'READ_ONLY',
  overlap_policy: 'SKIP',
}

export function AutomationsPage() {
  const qc = useQueryClient()
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<AutomationJobCreate>(EMPTY_FORM)
  const [formError, setFormError] = useState<string | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['automation-jobs'],
    queryFn: () => automationApi.list(),
    retry: false,
  })

  const { data: executions } = useQuery({
    queryKey: ['automation-executions', selectedJobId],
    queryFn: () => automationApi.executions(selectedJobId!),
    enabled: selectedJobId !== null,
    retry: false,
  })

  const createMut = useMutation({
    mutationFn: (body: AutomationJobCreate) => automationApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['automation-jobs'] })
      setShowForm(false)
      setForm(EMPTY_FORM)
      setFormError(null)
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      enabled ? automationApi.enable(id) : automationApi.disable(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automation-jobs'] }),
  })

  const triggerMut = useMutation({
    mutationFn: (id: number) => automationApi.trigger(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['automation-jobs'] })
      if (selectedJobId !== null)
        qc.invalidateQueries({ queryKey: ['automation-executions', selectedJobId] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => automationApi.delete(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['automation-jobs'] })
      if (selectedJobId === id) setSelectedJobId(null)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    createMut.mutate(form)
  }

  const jobs = data?.jobs ?? []

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>Automations</h2>
        <button className={styles.btnPrimary} onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New Job'}
        </button>
      </div>

      {showForm && (
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.formRow}>
            <label className={styles.label}>Name</label>
            <input
              className={styles.input}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              placeholder="morning-report"
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.label}>Schedule (cron)</label>
            <input
              className={styles.input}
              value={form.schedule}
              onChange={(e) => setForm({ ...form, schedule: e.target.value })}
              required
              placeholder="0 8 * * *"
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.label}>Action type</label>
            <input
              className={styles.input}
              value={form.action_type}
              onChange={(e) => setForm({ ...form, action_type: e.target.value })}
              required
              placeholder="tool"
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.label}>Description</label>
            <input
              className={styles.input}
              value={form.description ?? ''}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Optional description"
            />
          </div>
          <div className={styles.formRow}>
            <label className={styles.label}>Permission ceiling</label>
            <select
              className={styles.input}
              value={form.permission_ceiling}
              onChange={(e) => setForm({ ...form, permission_ceiling: e.target.value })}
            >
              <option value="READ_ONLY">Read-only</option>
              <option value="LOW_RISK">Low-risk</option>
            </select>
          </div>
          <div className={styles.formRow}>
            <label className={styles.label}>Overlap policy</label>
            <select
              className={styles.input}
              value={form.overlap_policy}
              onChange={(e) => setForm({ ...form, overlap_policy: e.target.value })}
            >
              <option value="SKIP">Skip</option>
              <option value="QUEUE">Queue</option>
              <option value="REPLACE">Replace</option>
              <option value="ALLOW">Allow</option>
            </select>
          </div>
          {formError && <p className={styles.error}>{formError}</p>}
          <button className={styles.btnPrimary} type="submit" disabled={createMut.isPending}>
            {createMut.isPending ? 'Creating…' : 'Create Job'}
          </button>
        </form>
      )}

      {isLoading && <p className={styles.muted}>Loading jobs…</p>}
      {error && <p className={styles.error}>Failed to load jobs — automation may be disabled.</p>}

      {!isLoading && !error && jobs.length === 0 && (
        <p className={styles.muted}>No automation jobs configured. Create one above.</p>
      )}

      {jobs.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Name</th>
                <th className={styles.th}>Schedule</th>
                <th className={styles.th}>Ceiling</th>
                <th className={styles.th}>Overlap</th>
                <th className={styles.th}>Last run</th>
                <th className={styles.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  selected={selectedJobId === job.id}
                  onToggle={(id, enabled) => toggleMut.mutate({ id, enabled })}
                  onTrigger={(id) => triggerMut.mutate(id)}
                  onDelete={(id) => deleteMut.mutate(id)}
                  onSelect={(id) => setSelectedJobId(id === selectedJobId ? null : id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedJobId !== null && (
        <div className={styles.execPanel}>
          <h3 className={styles.execTitle}>
            Execution history — {jobs.find((j) => j.id === selectedJobId)?.name}
          </h3>
          {!executions || executions.length === 0 ? (
            <p className={styles.muted}>No executions yet.</p>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Status</th>
                  <th className={styles.th}>Scheduled</th>
                  <th className={styles.th}>Started</th>
                  <th className={styles.th}>Completed</th>
                  <th className={styles.th}>Summary / Error</th>
                </tr>
              </thead>
              <tbody>
                {executions.map((ex) => (
                  <tr key={ex.execution_id} className={styles.row}>
                    <td className={styles.cell}>
                      <span className={`${styles.badge} ${STATUS_BADGE[ex.status] ?? ''}`}>
                        {ex.status}
                      </span>
                    </td>
                    <td className={styles.cell}>{new Date(ex.scheduled_time).toLocaleString()}</td>
                    <td className={styles.cell}>
                      {ex.actual_start_time ? new Date(ex.actual_start_time).toLocaleString() : '—'}
                    </td>
                    <td className={styles.cell}>
                      {ex.completion_time ? new Date(ex.completion_time).toLocaleString() : '—'}
                    </td>
                    <td className={styles.cell}>{ex.result_summary ?? ex.error ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
