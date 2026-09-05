import { useQuery } from '@tanstack/react-query'
import { healthApi } from '@/services/api/client'
import { useHudStore } from '@/app/stores/hudStore'
import styles from './HealthStrip.module.css'

const STATUS_ICONS: Record<string, string> = {
  healthy: '●',
  degraded: '◐',
  unhealthy: '○',
  not_configured: '·',
}

export function HealthStrip() {
  const setHealth = useHudStore((s) => s.setHealth)

  const { data } = useQuery({
    queryKey: ['health', 'dependencies'],
    queryFn: async () => {
      const result = await healthApi.dependencies()
      setHealth(result)
      return result
    },
    refetchInterval: 15_000,
    retry: false,
  })

  if (!data) return <div className={styles.strip} aria-label="Health status loading" />

  return (
    <footer className={styles.strip} role="contentinfo" aria-label="System health">
      {data.dependencies.map((dep) => (
        <span
          key={dep.name}
          className={`${styles.item} ${styles[dep.status]}`}
          title={dep.detail ?? dep.status}
          aria-label={`${dep.name}: ${dep.status}`}
        >
          <span aria-hidden="true">{STATUS_ICONS[dep.status] ?? '?'}</span>
          {' '}
          {dep.name.toUpperCase()}
        </span>
      ))}
    </footer>
  )
}
