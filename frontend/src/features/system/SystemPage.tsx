import { useQuery } from '@tanstack/react-query'
import { healthApi } from '@/services/api/client'
import styles from './SystemPage.module.css'

const STATUS_LABELS: Record<string, string> = {
  healthy: 'HEALTHY',
  degraded: 'DEGRADED',
  unhealthy: 'UNHEALTHY',
  not_configured: 'NOT CONFIGURED',
}

export function SystemPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['health', 'dependencies'],
    queryFn: healthApi.dependencies,
    refetchInterval: 15_000,
    retry: false,
  })

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>System Status</h1>
        <button
          className={styles.refreshBtn}
          onClick={() => void refetch()}
          aria-label="Refresh status"
        >
          ↻ Refresh
        </button>
      </div>

      {isLoading && (
        <div className={styles.loading} aria-live="polite">Checking dependencies…</div>
      )}

      {error && (
        <div className={styles.error} role="alert">
          Cannot reach JARVIS backend. Is it running on port 8000?
        </div>
      )}

      {data && (
        <>
          <div className={`${styles.overallBadge} ${styles[data.jarvis.toLowerCase()]}`}>
            JARVIS: {data.jarvis}
          </div>

          <ul className={styles.depList} role="list" aria-label="Dependency status">
            {data.dependencies.map((dep) => (
              <li key={dep.name} className={styles.depItem}>
                <div className={styles.depLeft}>
                  <span
                    className={`${styles.statusDot} ${styles[dep.status]}`}
                    aria-hidden="true"
                  />
                  <span className={styles.depName}>{dep.name.toUpperCase()}</span>
                </div>
                <div className={styles.depRight}>
                  <span className={`${styles.statusLabel} ${styles[dep.status]}`}>
                    {STATUS_LABELS[dep.status] ?? dep.status}
                  </span>
                  {dep.detail && (
                    <span className={styles.depDetail}>{dep.detail}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
