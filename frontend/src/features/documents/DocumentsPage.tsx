import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { documentsApi } from '@/services/api/client'
import type { DocumentOut } from '@/types/api'
import styles from './DocumentsPage.module.css'

const STATUS_COLORS: Record<string, string> = {
  INDEXED: 'healthy',
  FAILED: 'unhealthy',
  PARSING: 'info',
  CHUNKING: 'info',
  EMBEDDING: 'info',
  INDEXING: 'info',
  DISCOVERED: 'info',
  STALE: 'degraded',
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function DocumentsPage() {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const { data: documents, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: documentsApi.list,
    refetchInterval: 5000,
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => documentsApi.ingest(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      setUploadError(null)
    },
    onError: (err) => setUploadError(err instanceof Error ? err.message : 'Upload failed'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => documentsApi.delete(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['documents'] }),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadMutation.mutate(file)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Knowledge Base</h1>
        <div className={styles.actions}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.pdf,.docx"
            onChange={handleFileChange}
            className={styles.fileInput}
            aria-label="Upload document"
            id="doc-upload"
          />
          <label
            htmlFor="doc-upload"
            className={`${styles.uploadBtn} ${uploadMutation.isPending ? styles.uploading : ''}`}
            aria-busy={uploadMutation.isPending}
          >
            {uploadMutation.isPending ? '⟳ Ingesting…' : '+ Ingest Document'}
          </label>
        </div>
      </div>

      {uploadError && (
        <div className={styles.error} role="alert">
          ⚠ {uploadError}
          <button onClick={() => setUploadError(null)} aria-label="Dismiss">✕</button>
        </div>
      )}

      {isLoading && <div className={styles.loading}>Loading documents…</div>}

      {documents && documents.length === 0 && (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>📄</div>
          <div>No documents ingested yet.</div>
          <div className={styles.emptyHint}>
            Upload TXT, Markdown, PDF, or DOCX files to build your knowledge base.
          </div>
        </div>
      )}

      {documents && documents.length > 0 && (
        <ul className={styles.docList} role="list" aria-label="Documents">
          {documents.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              onDelete={() => deleteMutation.mutate(doc.id)}
              deleting={deleteMutation.isPending}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

function DocumentRow({
  doc,
  onDelete,
  deleting,
}: {
  doc: DocumentOut
  onDelete: () => void
  deleting: boolean
}) {
  const statusClass = STATUS_COLORS[doc.status] ?? 'neutral'

  return (
    <li className={styles.docItem}>
      <div className={styles.docLeft}>
        <span className={`${styles.statusDot} ${styles[statusClass]}`} aria-hidden="true" />
        <div className={styles.docInfo}>
          <span className={styles.docName}>{doc.filename}</span>
          <span className={styles.docMeta}>
            {doc.file_type.toUpperCase()} · {formatBytes(doc.file_size_bytes)}
            {doc.chunk_count > 0 && ` · ${doc.chunk_count} chunks`}
            {doc.embedding_model && ` · ${doc.embedding_model}`}
          </span>
          {doc.error_message && (
            <span className={styles.docError}>{doc.error_message}</span>
          )}
        </div>
      </div>
      <div className={styles.docRight}>
        <span className={`${styles.statusLabel} ${styles[statusClass]}`}>{doc.status}</span>
        <button
          className={styles.deleteBtn}
          onClick={onDelete}
          disabled={deleting}
          aria-label={`Delete ${doc.filename}`}
        >
          ✕
        </button>
      </div>
    </li>
  )
}
