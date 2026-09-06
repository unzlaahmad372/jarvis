import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { pluginsApi } from '@/services/api/client'
import styles from './PluginsPage.module.css'

export function PluginsPage() {
  const queryClient = useQueryClient()

  const { data: plugins = [], isLoading } = useQuery({
    queryKey: ['plugins'],
    queryFn: pluginsApi.list,
  })

  const reloadMutation = useMutation({
    mutationFn: pluginsApi.reload,
    onSuccess: (data) => queryClient.setQueryData(['plugins'], data),
  })

  const loaded = plugins.filter((p) => p.loaded)
  const failed = plugins.filter((p) => !p.loaded)

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Plugins</h1>
          <p className={styles.subtitle}>Drop <code>.py</code> files into <code>data/plugins/</code> — each must export <code>plugin_tool</code>.</p>
        </div>
        <button className={styles.reloadBtn} onClick={() => reloadMutation.mutate()} disabled={reloadMutation.isPending}>
          {reloadMutation.isPending ? '⟳ Reloading…' : '↺ Reload'}
        </button>
      </div>

      {isLoading && <div className={styles.loading}>Scanning plugins…</div>}

      {plugins.length === 0 && !isLoading && (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>🔌</div>
          <div>No plugins found in <code>data/plugins/</code></div>
          <div className={styles.emptyHint}>Create a <code>.py</code> file with a <code>plugin_tool</code> variable pointing to a BaseTool instance.</div>
        </div>
      )}

      {loaded.length > 0 && (
        <>
          <div className={styles.groupLabel}>Loaded ({loaded.length})</div>
          <ul className={styles.list}>
            {loaded.map((p) => (
              <li key={p.name} className={styles.item}>
                <div className={styles.itemLeft}>
                  <span className={styles.dot} style={{ background: 'var(--hud-success)' }} />
                  <div className={styles.itemInfo}>
                    <span className={styles.itemName}>{p.name}</span>
                    <span className={styles.itemDesc}>{p.description}</span>
                  </div>
                </div>
                <div className={styles.itemRight}>
                  <span className={styles.riskBadge} data-risk={p.risk_level}>{p.risk_level}</span>
                  <span className={styles.fileName}>{p.file}</span>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {failed.length > 0 && (
        <>
          <div className={styles.groupLabel} style={{ color: 'var(--hud-danger)' }}>Failed ({failed.length})</div>
          <ul className={styles.list}>
            {failed.map((p) => (
              <li key={p.file} className={`${styles.item} ${styles.itemFailed}`}>
                <div className={styles.itemLeft}>
                  <span className={styles.dot} style={{ background: 'var(--hud-danger)' }} />
                  <div className={styles.itemInfo}>
                    <span className={styles.itemName}>{p.file}</span>
                    <span className={styles.itemError}>{p.error}</span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className={styles.exampleBox}>
        <div className={styles.exampleTitle}>Example plugin (data/plugins/hello.py)</div>
        <pre className={styles.code}>{`from app.tools.base import BaseTool, ToolResult

class HelloTool(BaseTool):
    name = "hello"
    description = "Says hello"
    risk_level = "READ_ONLY"
    parameters_schema = {}

    async def run(self, **kwargs) -> ToolResult:
        return ToolResult(output="Hello from plugin!")

plugin_tool = HelloTool()`}</pre>
      </div>
    </div>
  )
}
