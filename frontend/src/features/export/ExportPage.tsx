import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { conversationsApi } from '@/services/api/client'
import styles from './ExportPage.module.css'

const BASE = ''

function download(url: string, filename: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
}

export function ExportPage() {
  const [fmt, setFmt] = useState<'markdown' | 'json' | 'txt'>('markdown')
  const [exporting, setExporting] = useState<number | null>(null)

  const { data: convs = [], isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: conversationsApi.list,
  })

  const exportOne = async (id: number, title: string | null) => {
    setExporting(id)
    try {
      const res = await fetch(`${BASE}/api/v1/export/conversations/${id}?format=${fmt}`)
      const blob = await res.blob()
      const ext = fmt === 'markdown' ? 'md' : fmt
      const name = (title ?? `conv-${id}`).replace(/[^a-z0-9]/gi, '-').toLowerCase()
      download(URL.createObjectURL(blob), `${name}.${ext}`)
    } finally {
      setExporting(null)
    }
  }

  const exportAll = async () => {
    setExporting(-1)
    try {
      const res = await fetch(`${BASE}/api/v1/export/conversations?format=json`)
      const blob = await res.blob()
      download(URL.createObjectURL(blob), 'jarvis-export.json')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Export Conversations</h1>
        <div className={styles.controls}>
          <select className={styles.select} value={fmt} onChange={(e) => setFmt(e.target.value as typeof fmt)}>
            <option value="markdown">Markdown (.md)</option>
            <option value="txt">Plain text (.txt)</option>
            <option value="json">JSON (.json)</option>
          </select>
          <button className={styles.exportAllBtn} onClick={() => void exportAll()} disabled={exporting === -1}>
            {exporting === -1 ? '⟳ Exporting…' : '⬇ Export All (JSON)'}
          </button>
        </div>
      </div>

      {isLoading && <div className={styles.loading}>Loading conversations…</div>}

      {convs.length === 0 && !isLoading && (
        <div className={styles.empty}>No conversations to export.</div>
      )}

      <ul className={styles.list}>
        {convs.map((c) => (
          <li key={c.id} className={styles.item}>
            <div className={styles.itemInfo}>
              <span className={styles.itemTitle}>{c.title ?? `conv #${c.id}`}</span>
              <span className={styles.itemDate}>{new Date(c.updated_at).toLocaleDateString()}</span>
            </div>
            <button
              className={styles.exportBtn}
              onClick={() => void exportOne(c.id, c.title)}
              disabled={exporting === c.id}
            >
              {exporting === c.id ? '⟳' : '⬇'}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
