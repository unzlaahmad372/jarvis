import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { workspacesApi } from '@/services/api/client'
import styles from './WorkspacePage.module.css'

export function WorkspacePage() {
  const queryClient = useQueryClient()
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: workspaces = [], isLoading } = useQuery({
    queryKey: ['workspaces'],
    queryFn: workspacesApi.list,
  })

  const createMutation = useMutation({
    mutationFn: () => workspacesApi.create({ name: newName.trim(), description: newDesc.trim() || undefined }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['workspaces'] })
      setNewName(''); setNewDesc(''); setError(null)
    },
    onError: (e) => setError(e instanceof Error ? e.message : 'Failed'),
  })

  const activateMutation = useMutation({
    mutationFn: (id: number) => workspacesApi.activate(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['workspaces'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => workspacesApi.delete(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['workspaces'] }),
    onError: (e) => setError(e instanceof Error ? e.message : 'Failed'),
  })

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Workspaces</h1>
      <p className={styles.subtitle}>Isolate conversations and documents by project or context.</p>

      {error && <div className={styles.error}>⚠ {error}<button onClick={() => setError(null)}>✕</button></div>}

      <div className={styles.createBox}>
        <input className={styles.input} placeholder="Workspace name" value={newName}
          onChange={(e) => setNewName(e.target.value)} />
        <input className={styles.input} placeholder="Description (optional)" value={newDesc}
          onChange={(e) => setNewDesc(e.target.value)} />
        <button className={styles.createBtn}
          disabled={!newName.trim() || createMutation.isPending}
          onClick={() => createMutation.mutate()}>
          {createMutation.isPending ? '⟳' : '+ Create'}
        </button>
      </div>

      {isLoading && <div className={styles.loading}>Loading…</div>}

      <ul className={styles.list}>
        {workspaces.map((ws) => (
          <li key={ws.id} className={`${styles.item} ${ws.is_default ? styles.active : ''}`}>
            <div className={styles.itemInfo}>
              <span className={styles.itemName}>
                {ws.is_default && <span className={styles.defaultBadge}>ACTIVE</span>}
                {ws.name}
              </span>
              {ws.description && <span className={styles.itemDesc}>{ws.description}</span>}
              <span className={styles.itemMeta}>{ws.conversation_count} conversation{ws.conversation_count !== 1 ? 's' : ''}</span>
            </div>
            <div className={styles.itemActions}>
              {!ws.is_default && (
                <>
                  <button className={styles.activateBtn}
                    onClick={() => activateMutation.mutate(ws.id)}
                    disabled={activateMutation.isPending}>
                    Activate
                  </button>
                  <button className={styles.deleteBtn}
                    onClick={() => deleteMutation.mutate(ws.id)}
                    disabled={deleteMutation.isPending}>
                    ✕
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
