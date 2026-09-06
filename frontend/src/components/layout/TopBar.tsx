import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useHudStore } from '@/app/stores/hudStore'
import { useChatStore } from '@/app/stores/chatStore'
import { JarvisCore } from '@/components/hud/JarvisCore'
import type { CoreState } from '@/components/hud/JarvisCore'
import { modelsApi } from '@/services/api/client'
import styles from './TopBar.module.css'

function useClock() {
  const [time, setTime] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// ── Model switcher ────────────────────────────────────────────────────────────

function ModelSwitcher() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data: active } = useQuery({
    queryKey: ['model-active'],
    queryFn: () => modelsApi.getActive(),
    staleTime: 30_000,
  })

  const { data: available } = useQuery({
    queryKey: ['models'],
    queryFn: () => modelsApi.list(),
    staleTime: 60_000,
    enabled: open,
  })

  const switchMutation = useMutation({
    mutationFn: (model: string) => modelsApi.setActive(model),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['model-active'] })
      setOpen(false)
    },
  })

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const label = active?.model ?? '…'

  return (
    <div className={styles.modelSwitcher} ref={ref}>
      <button
        className={`${styles.modelChipBtn} ${open ? styles.modelChipOpen : ''}`}
        onClick={() => setOpen((v) => !v)}
        title="Switch model"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Active model: ${label}. Click to switch.`}
      >
        ◈ {label}
        <span className={styles.modelChevron} aria-hidden="true">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className={styles.modelDropdown} role="listbox" aria-label="Available models">
          {!available && (
            <div className={styles.modelDropdownEmpty}>Loading…</div>
          )}
          {available?.models.length === 0 && (
            <div className={styles.modelDropdownEmpty}>No models found</div>
          )}
          {available?.models.map((m) => (
            <button
              key={m.name}
              className={`${styles.modelOption} ${m.name === active?.model ? styles.modelOptionActive : ''}`}
              onClick={() => switchMutation.mutate(m.name)}
              disabled={switchMutation.isPending}
              role="option"
              aria-selected={m.name === active?.model}
            >
              <span className={styles.modelOptionName}>{m.name}</span>
              {m.size_gb != null && (
                <span className={styles.modelOptionMeta}>{m.size_gb}GB</span>
              )}
              {m.family && (
                <span className={styles.modelOptionMeta}>{m.family}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── TopBar ────────────────────────────────────────────────────────────────────

export function TopBar() {
  const { mode, toggleMode, health } = useHudStore()
  const { jarvisState } = useChatStore()
  const clock = useClock()

  const overallStatus = health?.jarvis ?? null

  return (
    <header className={styles.topBar} role="banner">
      <div className={styles.brand}>
        <JarvisCore state={(({
          IDLE: 'IDLE', LISTENING: 'LISTENING', THINKING: 'THINKING',
          USING_TOOL: 'THINKING', WAITING_FOR_APPROVAL: 'THINKING',
          ERROR: 'ERROR', OFFLINE: 'OFFLINE',
        } as Record<string, string>)[jarvisState] ?? 'IDLE') as CoreState} size={36} />
        <span className={styles.brandName}>JARVIS</span>
        <span className={styles.brandVersion}>v0.1</span>
      </div>

      <div className={styles.center}>
        <ModelSwitcher />
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
