import { useEffect, useRef, useState } from 'react'
import { memoryApi } from '@/services/api/client'
import type { MemoryOut } from '@/types/api'
import styles from './MemoryPage.module.css'

const CATEGORIES = ['fact', 'preference', 'decision', 'project', 'entity', 'other']

const CATEGORY_COLORS: Record<string, string> = {
  fact: 'var(--hud-info)',
  preference: 'var(--hud-accent)',
  decision: 'var(--hud-warning)',
  project: 'var(--hud-success)',
  entity: 'var(--hud-text-secondary)',
  other: 'var(--hud-text-secondary)',
}

export function MemoryPage() {
  const [memories, setMemories] = useState<MemoryOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterCategory, setFilterCategory] = useState<string>('')
  const [content, setContent] = useState('')
  const [category, setCategory] = useState('fact')
  const [importance, setImportance] = useState(5)
  const [submitting, setSubmitting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const load = async (cat?: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await memoryApi.list(cat || undefined)
      setMemories(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load memories')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(filterCategory)
  }, [filterCategory])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!content.trim()) return
    setSubmitting(true)
    try {
      const m = await memoryApi.create({ content: content.trim(), category, importance })
      setMemories((prev) => [m, ...prev])
      setContent('')
      textareaRef.current?.focus()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save memory')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await memoryApi.delete(id)
      setMemories((prev) => prev.filter((m) => m.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete memory')
    }
  }

  const handlePurge = async () => {
    if (!window.confirm('Purge ALL memories? This cannot be undone.')) return
    try {
      await memoryApi.purge()
      setMemories([])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to purge memories')
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>LONG-TERM MEMORY</h1>
        <span className={styles.count}>{memories.length} entries</span>
      </header>

      {/* Add memory form */}
      <form className={styles.form} onSubmit={handleAdd}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          placeholder='Remember that… (e.g. "Phoenix GA target is Q3")'
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={3}
          aria-label="Memory content"
        />
        <div className={styles.formRow}>
          <select
            className={styles.select}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            aria-label="Category"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <label className={styles.importanceLabel}>
            Importance
            <input
              type="number"
              className={styles.importanceInput}
              min={1}
              max={10}
              value={importance}
              onChange={(e) => setImportance(Number(e.target.value))}
              aria-label="Importance 1-10"
            />
          </label>
          <button
            type="submit"
            className={styles.addBtn}
            disabled={submitting || !content.trim()}
          >
            {submitting ? 'Saving…' : 'Remember'}
          </button>
        </div>
      </form>

      {/* Filter bar */}
      <div className={styles.filterBar}>
        <span className={styles.filterLabel}>Filter:</span>
        {['', ...CATEGORIES].map((c) => (
          <button
            key={c || 'all'}
            className={`${styles.filterBtn} ${filterCategory === c ? styles.filterActive : ''}`}
            onClick={() => setFilterCategory(c)}
          >
            {c || 'all'}
          </button>
        ))}
        {memories.length > 0 && (
          <button className={styles.purgeBtn} onClick={handlePurge}>
            Purge all
          </button>
        )}
      </div>

      {error && <p className={styles.error} role="alert">{error}</p>}

      {loading ? (
        <p className={styles.empty}>Loading…</p>
      ) : memories.length === 0 ? (
        <p className={styles.empty}>No memories yet. Use the form above or say "remember that…" in chat.</p>
      ) : (
        <ul className={styles.list} role="list">
          {memories.map((m) => (
            <li key={m.id} className={styles.item}>
              <div className={styles.itemHeader}>
                <span
                  className={styles.categoryBadge}
                  style={{ color: CATEGORY_COLORS[m.category] ?? 'var(--hud-text-secondary)' }}
                >
                  {m.category}
                </span>
                <span className={styles.importance} title="Importance">
                  {'★'.repeat(Math.round(m.importance / 2))}
                </span>
                {m.source && (
                  <span className={styles.source}>{m.source}</span>
                )}
                <button
                  className={styles.deleteBtn}
                  onClick={() => handleDelete(m.id)}
                  aria-label={`Forget: ${m.content.slice(0, 40)}`}
                >
                  Forget
                </button>
              </div>
              <p className={styles.content}>{m.content}</p>
              <time className={styles.timestamp} dateTime={m.created_at}>
                {new Date(m.created_at).toLocaleString()}
              </time>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
