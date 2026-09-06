import { useQuery } from '@tanstack/react-query'
import { mcpApi } from '@/services/api/client'
import styles from './MCPPage.module.css'

export function MCPPage() {
  const { data: servers, isLoading } = useQuery({
    queryKey: ['mcp-servers'],
    queryFn: () => mcpApi.listServers(),
    refetchInterval: 30_000,
  })

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>MCP SERVERS</span>
        <span className={styles.subtitle}>Model Context Protocol</span>
      </div>

      {isLoading && <div className={styles.loading}>Connecting…</div>}

      {servers?.length === 0 && (
        <div className={styles.empty}>
          No MCP servers configured.
          <br />
          Set <code>JARVIS_MCP_SERVERS</code> to a JSON array of server configs.
        </div>
      )}

      <div className={styles.serverList}>
        {servers?.map((server) => (
          <ServerCard key={server.id} serverId={server.id} toolCount={server.tool_count} tools={server.tools} />
        ))}
      </div>
    </div>
  )
}

function ServerCard({
  serverId,
  toolCount,
  tools,
}: {
  serverId: string
  toolCount: number
  tools: string[]
}) {
  const { data: toolDetails } = useQuery({
    queryKey: ['mcp-tools', serverId],
    queryFn: () => mcpApi.listServerTools(serverId),
  })

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.serverId}>{serverId}</span>
        <span className={styles.badge}>{toolCount} tools</span>
      </div>
      <div className={styles.toolGrid}>
        {(toolDetails ?? tools.map((t) => ({ name: t, description: '', input_schema: {} }))).map((tool) => (
          <div key={tool.name} className={styles.tool}>
            <span className={styles.toolName}>{tool.name}</span>
            {tool.description && (
              <span className={styles.toolDesc}>{tool.description}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
