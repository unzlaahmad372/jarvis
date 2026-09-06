import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi } from '@/services/api/client'
import type { SettingsOut } from '@/types/api'
import styles from './SettingsPage.module.css'

type Draft = Partial<SettingsOut>

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className={styles.row}>
      <div className={styles.rowLabel}>
        <span>{label}</span>
        {hint && <span className={styles.hint}>{hint}</span>}
      </div>
      <div className={styles.rowControl}>{children}</div>
    </div>
  )
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Draft>({})
  const [saved, setSaved] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
    staleTime: 30_000,
  })

  const mutation = useMutation({
    mutationFn: (patch: Draft) => settingsApi.patch(patch),
    onSuccess: (updated) => {
      queryClient.setQueryData(['settings'], updated)
      setDraft({})
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  if (isLoading || !data) return <div className={styles.loading}>Loading settings…</div>

  const val = <K extends keyof SettingsOut>(key: K): SettingsOut[K] =>
    (draft[key] as SettingsOut[K]) ?? data[key]

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))

  const hasDraft = Object.keys(draft).length > 0

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Settings</h1>
        <div className={styles.headerActions}>
          {saved && <span className={styles.savedBadge}>✓ Saved</span>}
          <button
            className={styles.saveBtn}
            disabled={!hasDraft || mutation.isPending}
            onClick={() => mutation.mutate(draft)}
          >
            {mutation.isPending ? 'Saving…' : 'Apply Changes'}
          </button>
        </div>
      </div>

      <p className={styles.notice}>
        Changes apply immediately but reset on restart. Edit <code>.env</code> for permanent changes.
      </p>

      {mutation.isError && (
        <div className={styles.error}>⚠ {(mutation.error as Error).message}</div>
      )}

      <section className={styles.section}>
        <div className={styles.sectionTitle}>Model</div>
        <Row label="Chat model" hint="Ollama model name">
          <input className={styles.input} value={val('llm_model')} onChange={(e) => set('llm_model', e.target.value)} />
        </Row>
        <Row label="Embedding model" hint="Used for RAG">
          <input className={styles.input} value={val('embedding_model')} onChange={(e) => set('embedding_model', e.target.value)} />
        </Row>
        <Row label="Ollama URL">
          <input className={styles.input} value={data.ollama_url} disabled title="Change in .env" />
        </Row>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionTitle}>Context</div>
        <Row label="Max context tokens">
          <input className={styles.input} type="number" min={512} max={131072} value={val('max_context_tokens')}
            onChange={(e) => set('max_context_tokens', parseInt(e.target.value))} />
        </Row>
        <Row label="Max response tokens">
          <input className={styles.input} type="number" min={128} max={16384} value={val('max_response_tokens')}
            onChange={(e) => set('max_response_tokens', parseInt(e.target.value))} />
        </Row>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionTitle}>Voice</div>
        <Row label="Enable voice">
          <label className={styles.toggle}>
            <input type="checkbox" checked={val('enable_voice')} onChange={(e) => set('enable_voice', e.target.checked)} />
            <span className={styles.toggleSlider} />
          </label>
        </Row>
        <Row label="Auto-speak replies">
          <label className={styles.toggle}>
            <input type="checkbox" checked={val('voice_auto_speak')} onChange={(e) => set('voice_auto_speak', e.target.checked)} />
            <span className={styles.toggleSlider} />
          </label>
        </Row>
        <Row label="Always listening (wake word)">
          <label className={styles.toggle}>
            <input type="checkbox" checked={val('enable_always_listening')} onChange={(e) => set('enable_always_listening', e.target.checked)} />
            <span className={styles.toggleSlider} />
          </label>
        </Row>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionTitle}>Safety</div>
        <Row label="Require tool confirmation">
          <label className={styles.toggle}>
            <input type="checkbox" checked={val('require_confirmation')} onChange={(e) => set('require_confirmation', e.target.checked)} />
            <span className={styles.toggleSlider} />
          </label>
        </Row>
        <Row label="Enable vision">
          <label className={styles.toggle}>
            <input type="checkbox" checked={val('enable_vision')} onChange={(e) => set('enable_vision', e.target.checked)} />
            <span className={styles.toggleSlider} />
          </label>
        </Row>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionTitle}>Retention</div>
        <Row label="Conversation retention (days)">
          <input className={styles.input} type="number" min={1} max={3650} value={val('conversation_retention_days')}
            onChange={(e) => set('conversation_retention_days', parseInt(e.target.value))} />
        </Row>
        <Row label="Tool log retention (days)">
          <input className={styles.input} type="number" min={1} max={365} value={val('tool_log_retention_days')}
            onChange={(e) => set('tool_log_retention_days', parseInt(e.target.value))} />
        </Row>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionTitle}>Logging</div>
        <Row label="Log level">
          <select className={styles.select} value={val('log_level')} onChange={(e) => set('log_level', e.target.value)}>
            {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </Row>
      </section>
    </div>
  )
}
