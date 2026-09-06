import { useEffect, useState } from 'react'
import { useHudStore } from '@/app/stores/hudStore'
import { useChatStore } from '@/app/stores/chatStore'
import { JarvisCore } from '@/components/hud/JarvisCore'
import type { CoreState } from '@/components/hud/JarvisCore'
import styles from './TopBar.module.css'

function useClock() {
  const [time, setTime] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function TopBar() {
  const { mode, toggleMode, health } = useHudStore()
  const { jarvisState } = useChatStore()
  const clock = useClock()

  const overallStatus = health?.jarvis ?? null

  // Extract active model from health dependencies
  const modelDep = health?.dependencies.find((d) => d.name === 'ollama')
  const modelLabel = modelDep?.detail ?? null

  return (
    <header className={styles.topBar} role="banner">
      <div className={styles.brand}>
        <JarvisCore state={jarvisState as CoreState} size={36} />
        <span className={styles.brandName}>JARVIS</span>
        <span className={styles.brandVersion}>v0.1</span>
      </div>

      <div className={styles.center}>
        {modelLabel && (
          <span className={styles.modelChip} title="Active model">
            ◈ {modelLabel}
          </span>
        )}
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
        <span className={styles.clock} aria-label="Current time">{clock}</span>
        <button
          className={styles.modeToggle}
          onClick={toggleMode}
          aria-label={`Switch to ${mode === 'FOCUS' ? 'Command Center' : 'Focus'} mode`}
          title={`Current: ${mode === 'FOCUS' ? 'Focus' : 'Command Center'} mode`}
        >
          {mode === 'FOCUS' ? '⊞ CMD' : '◧ FOCUS'}
        </button>
      </div>
    </header>
  )
}
