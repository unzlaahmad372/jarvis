import { useQuery } from '@tanstack/react-query'
import { grafanaApi, jenkinsApi, prometheusApi, spinnakerApi } from '@/services/api/client'
import styles from './OperationsPage.module.css'

const RESULT_COLORS: Record<string, string> = {
  SUCCESS: 'var(--hud-success)',
  FAILURE: 'var(--hud-danger)',
  ABORTED: 'var(--hud-text-secondary)',
  UNSTABLE: 'var(--hud-warning)',
  SUCCEEDED: 'var(--hud-success)',
  TERMINAL: 'var(--hud-danger)',
  CANCELED: 'var(--hud-text-secondary)',
  RUNNING: 'var(--hud-info)',
}

function statusColor(s: string | null): string {
  return s ? (RESULT_COLORS[s] ?? 'var(--hud-text-secondary)') : 'var(--hud-text-secondary)'
}

function durationLabel(ms: number): string {
  if (ms < 60000) return `${Math.round(ms / 1000)}s`
  return `${Math.round(ms / 60000)}m`
}

export function OperationsPage() {
  const { data: jenkinsData, isLoading: jLoading, error: jError } = useQuery({
    queryKey: ['jenkins-jobs'],
    queryFn: () => jenkinsApi.jobs(),
    retry: false,
  })

  const { data: grafanaData, isLoading: gLoading, error: gError } = useQuery({
    queryKey: ['grafana-dashboards'],
    queryFn: () => grafanaApi.dashboards(),
    retry: false,
  })

  const { data: spinnakerData, isLoading: sLoading, error: sError } = useQuery({
    queryKey: ['spinnaker-phoenix-prewash'],
    queryFn: () => spinnakerApi.executions('phoenix', 'prewash', 5),
    retry: false,
  })

  const { data: promData, isLoading: pLoading, error: pError } = useQuery({
    queryKey: ['prometheus-up'],
    queryFn: () => prometheusApi.query('up'),
    retry: false,
  })

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>OPERATIONS</h1>
        <span className={styles.subtitle}>CI/CD &amp; Observability</span>
      </header>

      <div className={styles.grid}>

        {/* Jenkins */}
        <section className={styles.card}>
          <div className={styles.cardTitle}>JENKINS</div>
          {jLoading && <div className={styles.loading}>Loading…</div>}
          {jError && <div className={styles.disabled}>Not configured or unavailable</div>}
          {jenkinsData && jenkinsData.jobs.length === 0 && (
            <div className={styles.empty}>No jobs found</div>
          )}
          {jenkinsData?.jobs.map((job) => (
            <div key={job.name} className={styles.row}>
              <span className={styles.rowName}>{job.name}</span>
              {job.last_build ? (
                <>
                  <span className={styles.badge} style={{ color: statusColor(job.last_build.result) }}>
                    {job.last_build.result ?? 'RUNNING'}
                  </span>
                  <span className={styles.meta}>#{job.last_build.build_number}</span>
                  <span className={styles.meta}>{durationLabel(job.last_build.duration_ms)}</span>
                  {job.last_build.failed_stage && (
                    <span className={styles.failedStage}>↳ {job.last_build.failed_stage}</span>
                  )}
                  <a href={job.last_build.url} target="_blank" rel="noreferrer" className={styles.link}>↗</a>
                </>
              ) : (
                <span className={styles.meta}>No builds</span>
              )}
            </div>
          ))}
        </section>

        {/* Spinnaker */}
        <section className={styles.card}>
          <div className={styles.cardTitle}>SPINNAKER</div>
          {sLoading && <div className={styles.loading}>Loading…</div>}
          {sError && <div className={styles.disabled}>Not configured or unavailable</div>}
          {spinnakerData && spinnakerData.executions.length === 0 && (
            <div className={styles.empty}>No executions found</div>
          )}
          {spinnakerData?.executions.map((ex) => (
            <div key={ex.id} className={styles.row}>
              <span className={styles.rowName}>{ex.pipeline_name}</span>
              <span className={styles.badge} style={{ color: statusColor(ex.status) }}>
                {ex.status}
              </span>
              <span className={styles.meta}>{durationLabel(ex.duration_ms)}</span>
              {ex.stages.filter((s) => s.status === 'TERMINAL').map((s) => (
                <span key={s.name} className={styles.failedStage}>↳ {s.name}</span>
              ))}
              <a href={ex.url} target="_blank" rel="noreferrer" className={styles.link}>↗</a>
            </div>
          ))}
        </section>

        {/* Prometheus */}
        <section className={styles.card}>
          <div className={styles.cardTitle}>PROMETHEUS</div>
          {pLoading && <div className={styles.loading}>Loading…</div>}
          {pError && <div className={styles.disabled}>Not configured or unavailable</div>}
          {promData && promData.results.length === 0 && (
            <div className={styles.empty}>No metrics returned</div>
          )}
          {promData?.results.map((m, i) => (
            <div key={i} className={styles.row}>
              <span className={styles.rowName}>{m.metric}</span>
              <span className={styles.badge} style={{ color: 'var(--hud-accent)' }}>
                {m.value}
              </span>
              {Object.entries(m.labels).slice(0, 2).map(([k, v]) => (
                <span key={k} className={styles.meta}>{k}={v}</span>
              ))}
            </div>
          ))}
        </section>

        {/* Grafana */}
        <section className={styles.card}>
          <div className={styles.cardTitle}>GRAFANA</div>
          {gLoading && <div className={styles.loading}>Loading…</div>}
          {gError && <div className={styles.disabled}>Not configured or unavailable</div>}
          {grafanaData && grafanaData.dashboards.length === 0 && (
            <div className={styles.empty}>No dashboards found</div>
          )}
          {grafanaData?.dashboards.map((d) => (
            <div key={d.uid} className={styles.row}>
              <span className={styles.rowName}>{d.title}</span>
              {d.folder && <span className={styles.meta}>{d.folder}</span>}
              {d.tags.map((t) => (
                <span key={t} className={styles.tag}>{t}</span>
              ))}
              <a href={d.url} target="_blank" rel="noreferrer" className={styles.link}>↗</a>
            </div>
          ))}
        </section>

      </div>
    </div>
  )
}
