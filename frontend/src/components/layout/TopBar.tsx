import { useHudStore } from '@/app/stores/hudStore'
import styles from './TopBar.module.css'

export function TopBar() {
  const { mode, toggleMode, health } = useHudStore()

  const overallStatus = health?.jarvis ?? null

  return (
    <header className={styles.topBar} role="banner">
      <div className={styles.brand}>
        <span className={styles.brandName}>JARVIS</span>
        <span className={styles.brandVersion}>v0.1</span>
      </div>

      <div className={styles.center}>
        {overallStatus && (
          <span
            className={`${styles.statusChip} ${styles[`status_${overallStatus.toLowerCase()}`]}`}
            aria-label={`System status: ${overallStatus}`}
          >
            {overallStatus}
          </span>
        )}
      </div>

      <div className={styles.actions}>
        <button
          className={styles.modeToggle}
          onClick={toggleMode}
          aria-label={`Switch to ${mode === 'FOCUS' ? 'Command Center' : 'Focus'} mode`}
          title={`Current: ${mode === 'FOCUS' ? 'Focus' : 'Command Center'} mode`}
        >
          {mode === 'FOCUS' ? '⊞' : '◧'}
        </button>
      </div>
    </header>
  )
}
