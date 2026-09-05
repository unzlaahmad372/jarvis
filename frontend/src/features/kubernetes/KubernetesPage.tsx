import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { kubernetesApi } from '@/services/api/client'
import type { K8sClusterHealthOut } from '@/types/api'
import styles from './KubernetesPage.module.css'

function statusColor(status: string): string {
  if (status === 'HEALTHY') return 'var(--hud-success)'
  if (status === 'DEGRADED') return 'var(--hud-warning)'
  return 'var(--hud-danger)'
}

function HealthCard({ health }: { health: K8sClusterHealthOut }) {
  return (
    <div className={styles.healthCard}>
      <div className={styles.healthHeader}>
        <span className={styles.contextName}>{health.context}</span>
        {health.protected && <span className={styles.protectedBadge}>PROTECTED</span>}
        <span className={styles.statusBadge} style={{ color: statusColor(health.status) }}>
          {health.status}
        </span>
      </div>
      {health.error && <div className={styles.errorMsg}>{health.error}</div>}
      {health.reachable && (
        <div className={styles.healthMetrics}>
          <div className={styles.metric}>
            <span className={styles.metricLabel}>Nodes</span>
            <span className={styles.metricValue}>{health.node_ready}/{health.node_total}</span>
          </div>
          <div className={styles.metric}>
            <span className={styles.metricLabel}>Pods Running</span>
            <span className={styles.metricValue}>{health.pod_running}/{health.pod_total}</span>
          </div>
          {health.pod_failed > 0 && (
            <div className={styles.metric}>
              <span className={styles.metricLabel}>Failed</span>
              <span className={styles.metricValue} style={{ color: 'var(--hud-danger)' }}>
                {health.pod_failed}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function KubernetesPage() {
  const [selectedContext, setSelectedContext] = useState<string | null>(null)

  const { data: contextsData, isLoading: ctxLoading, error: ctxError } = useQuery({
    queryKey: ['k8s-contexts'],
    queryFn: () => kubernetesApi.contexts(),
    retry: false,
  })

  const { data: healthData, isLoading: healthLoading } = useQuery({
    queryKey: ['k8s-health', selectedContext],
    queryFn: () => kubernetesApi.health(selectedContext!),
    enabled: selectedContext != null,
    retry: false,
  })

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>Kubernetes</h2>
        <span className={styles.subtitle}>Read-only cluster inspection</span>
      </div>

      {ctxLoading && <div className={styles.loading}>Loading contexts…</div>}

      {ctxError && (
        <div className={styles.error}>
          {ctxError instanceof Error ? ctxError.message : 'Kubernetes unavailable'}
        </div>
      )}

      {contextsData && (
        <div className={styles.layout}>
          {/* Context list */}
          <div className={styles.contextList}>
            <div className={styles.sectionTitle}>Contexts</div>
            {contextsData.contexts.length === 0 && (
              <div className={styles.empty}>No kubeconfig found. Run <code>kubectl config</code> to add a cluster.</div>
            )}
            {contextsData.contexts.map((ctx) => (
              <button
                key={ctx.name}
                className={`${styles.contextItem} ${selectedContext === ctx.name ? styles.active : ''}`}
                onClick={() => setSelectedContext(ctx.name)}
                aria-pressed={selectedContext === ctx.name}
              >
                <span className={styles.ctxName}>{ctx.name}</span>
                <div className={styles.ctxMeta}>
                  {ctx.current && <span className={styles.currentBadge}>current</span>}
                  {ctx.protected && <span className={styles.protectedBadge}>protected</span>}
                </div>
                <span className={styles.ctxCluster}>{ctx.cluster}</span>
              </button>
            ))}
          </div>

          {/* Health panel */}
          <div className={styles.healthPanel}>
            {!selectedContext && (
              <div className={styles.empty}>Select a context to inspect cluster health</div>
            )}
            {healthLoading && <div className={styles.loading}>Querying cluster…</div>}
            {healthData && <HealthCard health={healthData} />}
          </div>
        </div>
      )}
    </div>
  )
}
