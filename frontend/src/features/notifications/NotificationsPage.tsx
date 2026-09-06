import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { automationApi } from '@/services/api/client'
import styles from './NotificationsPage.module.css'

type Permission = 'default' | 'granted' | 'denied'

function useBrowserNotifications() {
  const supported = typeof window !== 'undefined' && 'Notification' in window
  const [permission, setPermission] = useState<Permission>(
    supported ? (Notification.permission as Permission) : 'denied'
  )

  const request = async () => {
    if (!supported) return
    const result = await Notification.requestPermission()
    setPermission(result as Permission)
  }

  const send = (title: string, body: string) => {
    if (permission !== 'granted') return
    new Notification(title, { body, icon: '/favicon.ico' })
  }

  return { supported, permission, request, send }
}

export function NotificationsPage() {
  const notif = useBrowserNotifications()
  const [watchEnabled, setWatchEnabled] = useState(false)
  const [lastSeenIds, setLastSeenIds] = useState<Set<number>>(new Set())

  // Poll automation executions and fire notifications for new completions
  const { data: jobs = [] } = useQuery({
    queryKey: ['automation-jobs-notif'],
    queryFn: async () => {
      const res = await automationApi.list()
      return res.jobs
    },
    refetchInterval: watchEnabled ? 10_000 : false,
  })

  useEffect(() => {
    if (!watchEnabled || !jobs.length) return
    void (async () => {
      for (const job of jobs) {
        const execs = await automationApi.executions(job.id, 5)
        for (const ex of execs) {
          if (!lastSeenIds.has(ex.id) && (ex.status === 'SUCCESS' || ex.status === 'FAILED')) {
            notif.send(
              `JARVIS — ${job.name}`,
              `Job ${ex.status.toLowerCase()} at ${new Date(ex.completion_time ?? ex.created_at).toLocaleTimeString()}`
            )
            setLastSeenIds((s) => new Set([...s, ex.id]))
          }
        }
      }
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs, watchEnabled])

  const permColor = notif.permission === 'granted' ? 'var(--hud-success)'
    : notif.permission === 'denied' ? 'var(--hud-danger)' : 'var(--hud-warning)'

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Notifications</h1>
      <p className={styles.subtitle}>Desktop notifications for automation job completions.</p>

      <div className={styles.card}>
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Browser support</span>
          <span style={{ color: notif.supported ? 'var(--hud-success)' : 'var(--hud-danger)' }}>
            {notif.supported ? 'Supported' : 'Not supported'}
          </span>
        </div>
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Permission</span>
          <span style={{ color: permColor, fontFamily: 'var(--hud-font-mono)', fontSize: 'var(--hud-font-size-sm)', letterSpacing: '0.06em' }}>
            {notif.permission.toUpperCase()}
          </span>
        </div>
        {notif.permission !== 'granted' && notif.supported && (
          <div className={styles.cardRow}>
            <span className={styles.cardLabel}>Grant permission</span>
            <button className={styles.btn} onClick={() => void notif.request()}>
              Request Permission
            </button>
          </div>
        )}
        <div className={styles.cardRow}>
          <span className={styles.cardLabel}>Watch automation jobs</span>
          <label className={styles.toggle}>
            <input type="checkbox" checked={watchEnabled}
              disabled={notif.permission !== 'granted'}
              onChange={(e) => setWatchEnabled(e.target.checked)} />
            <span className={styles.toggleSlider} />
          </label>
        </div>
        {notif.permission === 'granted' && (
          <div className={styles.cardRow}>
            <span className={styles.cardLabel}>Test notification</span>
            <button className={styles.btn} onClick={() => notif.send('JARVIS', 'Notifications are working!')}>
              Send Test
            </button>
          </div>
        )}
      </div>

      <div className={styles.info}>
        <div className={styles.infoTitle}>How it works</div>
        <ul className={styles.infoList}>
          <li>Grant browser notification permission above</li>
          <li>Enable "Watch automation jobs" to poll every 10 seconds</li>
          <li>A desktop notification fires when any job completes or fails</li>
          <li>Works even when JARVIS is in a background tab</li>
        </ul>
      </div>
    </div>
  )
}
