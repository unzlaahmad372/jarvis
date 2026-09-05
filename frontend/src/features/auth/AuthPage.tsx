import { useEffect, useState } from 'react'
import { authApi } from '@/services/api/client'
import type { DeviceOut } from '@/types/api'
import styles from './AuthPage.module.css'

const DEVICE_TYPES = ['desktop', 'mobile', 'tablet', 'api']

export function AuthPage() {
  const [devices, setDevices] = useState<DeviceOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [deviceType, setDeviceType] = useState('desktop')
  const [registering, setRegistering] = useState(false)
  const [lastTokens, setLastTokens] = useState<{ access: string; refresh: string; scopes: string[] } | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setDevices(await authApi.listDevices())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load devices')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setRegistering(true)
    setError(null)
    setLastTokens(null)
    try {
      const resp = await authApi.registerDevice({ name: name.trim(), device_type: deviceType })
      setLastTokens({ access: resp.access_token, refresh: resp.refresh_token, scopes: resp.scopes })
      setName('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Registration failed')
    } finally {
      setRegistering(false)
    }
  }

  const handleRevoke = async (id: string) => {
    if (!window.confirm(`Revoke device ${id}?`)) return
    try {
      await authApi.revokeDevice(id)
      setDevices((prev) => prev.map((d) => d.device_id === id ? { ...d, revoked: true } : d))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Revoke failed')
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>DEVICE REGISTRY</h1>
        <span className={styles.count}>{devices.length} devices</span>
      </header>

      <form className={styles.form} onSubmit={handleRegister}>
        <input
          className={styles.input}
          placeholder="Device name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <select
          className={styles.select}
          value={deviceType}
          onChange={(e) => setDeviceType(e.target.value)}
        >
          {DEVICE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button className={styles.registerBtn} type="submit" disabled={registering || !name.trim()}>
          {registering ? 'Registering…' : 'Register Device'}
        </button>
      </form>

      {error && <p className={styles.error} role="alert">{error}</p>}

      {lastTokens && (
        <div className={styles.tokenBox}>
          <p className={styles.tokenNote}>⚠ Copy these tokens now — they will not be shown again.</p>
          <div className={styles.tokenRow}>
            <span className={styles.tokenLabel}>Scopes:</span>
            <span className={styles.mono}>{lastTokens.scopes.join(', ')}</span>
          </div>
          <div className={styles.tokenRow}>
            <span className={styles.tokenLabel}>Access token:</span>
            <code className={styles.tokenValue}>{lastTokens.access}</code>
          </div>
          <div className={styles.tokenRow}>
            <span className={styles.tokenLabel}>Refresh token:</span>
            <code className={styles.tokenValue}>{lastTokens.refresh}</code>
          </div>
        </div>
      )}

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : devices.length === 0 ? (
        <p className={styles.empty}>No devices registered.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Scopes</th>
              <th>Status</th>
              <th>Last seen</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => (
              <tr key={d.device_id} className={d.revoked ? styles.revoked : ''}>
                <td>{d.name}</td>
                <td className={styles.mono}>{d.device_type}</td>
                <td className={styles.mono}>{d.scopes.join(', ')}</td>
                <td className={d.revoked ? styles.revokedBadge : styles.activeBadge}>
                  {d.revoked ? 'REVOKED' : 'ACTIVE'}
                </td>
                <td className={styles.mono}>
                  {d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : '—'}
                </td>
                <td>
                  {!d.revoked && (
                    <button className={styles.revokeBtn} onClick={() => void handleRevoke(d.device_id)}>
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
