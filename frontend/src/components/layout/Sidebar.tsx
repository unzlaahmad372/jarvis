import { useState, useEffect, useRef } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { conversationsApi } from '@/services/api/client'
import { useChatStore } from '@/app/stores/chatStore'
import type { ConversationOut } from '@/types/api'
import styles from './Sidebar.module.css'

const ICONS: Record<string, JSX.Element> = {
  chat: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 4h16v10H11l-4 3v-3H2z" strokeLinejoin="round" />
    </svg>
  ),
  documents: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="4" y="2" width="12" height="16" rx="1" />
      <line x1="7" y1="7" x2="13" y2="7" />
      <line x1="7" y1="10" x2="13" y2="10" />
      <line x1="7" y1="13" x2="11" y2="13" />
    </svg>
  ),
  memory: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="10" cy="10" r="7" />
      <circle cx="10" cy="10" r="3" />
      <line x1="10" y1="3" x2="10" y2="7" />
      <line x1="10" y1="13" x2="10" y2="17" />
      <line x1="3" y1="10" x2="7" y2="10" />
      <line x1="13" y1="10" x2="17" y2="10" />
    </svg>
  ),
  tools: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M14 2l-2 2 4 4 2-2-4-4z" />
      <path d="M12 4L4 12l1 3 3 1 8-8-4-4z" />
    </svg>
  ),
  kubernetes: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <polygon points="10,2 18,7 18,13 10,18 2,13 2,7" />
      <circle cx="10" cy="10" r="2.5" />
      <line x1="10" y1="2" x2="10" y2="7.5" />
      <line x1="10" y1="12.5" x2="10" y2="18" />
      <line x1="2" y1="7" x2="7" y2="9" />
      <line x1="13" y1="11" x2="18" y2="13" />
      <line x1="2" y1="13" x2="7" y2="11" />
      <line x1="13" y1="9" x2="18" y2="7" />
    </svg>
  ),
  operations: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M10 2 L10 6 M10 14 L10 18 M2 10 L6 10 M14 10 L18 10" />
      <circle cx="10" cy="10" r="4" />
      <circle cx="10" cy="10" r="1.5" fill="currentColor" />
    </svg>
  ),
  automations: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="10" cy="10" r="7" />
      <polyline points="10,6 10,10 13,13" strokeLinecap="round" />
    </svg>
  ),
  backup: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M10 3v10M6 9l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 15h12" strokeLinecap="round" />
    </svg>
  ),
  devices: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="5" width="14" height="10" rx="1" />
      <line x1="7" y1="15" x2="7" y2="17" />
      <line x1="13" y1="15" x2="13" y2="17" />
      <line x1="5" y1="17" x2="15" y2="17" />
    </svg>
  ),
  audit: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="4" y="2" width="12" height="16" rx="1" />
      <line x1="7" y1="6" x2="13" y2="6" />
      <line x1="7" y1="9" x2="13" y2="9" />
      <line x1="7" y1="12" x2="10" y2="12" />
      <circle cx="13" cy="14" r="2.5" />
      <line x1="15" y1="16" x2="17" y2="18" strokeLinecap="round" />
    </svg>
  ),
  mcp: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="5" cy="10" r="2" />
      <circle cx="15" cy="5" r="2" />
      <circle cx="15" cy="15" r="2" />
      <line x1="7" y1="9" x2="13" y2="6" />
      <line x1="7" y1="11" x2="13" y2="14" />
    </svg>
  ),
  observe: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <polyline points="2,14 6,9 9,12 13,6 18,10" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  system: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="3" width="16" height="11" rx="1" />
      <line x1="6" y1="17" x2="14" y2="17" />
      <line x1="10" y1="14" x2="10" y2="17" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="10" cy="10" r="2.5" />
      <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.2 4.2l1.4 1.4M14.4 14.4l1.4 1.4M4.2 15.8l1.4-1.4M14.4 5.6l1.4-1.4" strokeLinecap="round" />
    </svg>
  ),
  export: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M10 3v10M6 9l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 15h14" strokeLinecap="round" />
    </svg>
  ),
  workspace: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="5" width="7" height="10" rx="1" />
      <rect x="11" y="5" width="7" height="10" rx="1" />
    </svg>
  ),
  notifications: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M10 2a6 6 0 0 1 6 6v3l2 2H2l2-2V8a6 6 0 0 1 6-6z" />
      <path d="M8 16a2 2 0 0 0 4 0" />
    </svg>
  ),
  plugins: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="3" width="6" height="6" rx="1" />
      <rect x="11" y="3" width="6" height="6" rx="1" />
      <rect x="3" y="11" width="6" height="6" rx="1" />
      <path d="M14 11v2m0 4v-2m0 0h-2m4 0h-2" strokeLinecap="round" />
    </svg>
  ),
}

const NAV_ITEMS = [
  { to: '/chat',          label: 'Chat',        icon: 'chat' },
  { to: '/documents',     label: 'Documents',   icon: 'documents' },
  { to: '/memory',        label: 'Memory',      icon: 'memory' },
  { to: '/tools',         label: 'Tools',       icon: 'tools' },
  { to: '/kubernetes',    label: 'Kubernetes',  icon: 'kubernetes' },
  { to: '/operations',    label: 'Operations',  icon: 'operations' },
  { to: '/automations',   label: 'Automations', icon: 'automations' },
  { to: '/backup',        label: 'Backup',      icon: 'backup' },
  { to: '/auth',          label: 'Devices',     icon: 'devices' },
  { to: '/audit',         label: 'Audit',       icon: 'audit' },
  { to: '/mcp',           label: 'MCP',         icon: 'mcp' },
  { to: '/observability', label: 'Observe',     icon: 'observe' },
  { to: '/system',        label: 'System',        icon: 'system' },
  { to: '/settings',      label: 'Settings',      icon: 'settings' },
  { to: '/export',        label: 'Export',        icon: 'export' },
  { to: '/workspace',     label: 'Workspaces',    icon: 'workspace' },
  { to: '/notifications', label: 'Alerts',        icon: 'notifications' },
  { to: '/plugins',       label: 'Plugins',       icon: 'plugins' },
] as const

// ── Date grouping ─────────────────────────────────────────────────────────────

function getGroup(dateStr: string): string {
  const now = new Date()
  const d = new Date(dateStr)
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000)
  if (diffDays < 1) return 'Today'
  if (diffDays < 2) return 'Yesterday'
  if (diffDays < 7) return 'This Week'
  return 'Older'
}

const GROUP_ORDER = ['Today', 'Yesterday', 'This Week', 'Older']

function groupConversations(convs: ConversationOut[]): [string, ConversationOut[]][] {
  const map = new Map<string, ConversationOut[]>()
  for (const c of convs) {
    const g = getGroup(c.updated_at)
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(c)
  }
  return GROUP_ORDER.filter((g) => map.has(g)).map((g) => [g, map.get(g)!])
}

// ── Conversation panel ────────────────────────────────────────────────────────

function ConversationPanel() {
  const navigate = useNavigate()
  const { activeConversationId, setActiveConversation } = useChatStore()
  const [query, setQuery] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setDebouncedQ(query.trim()), 300)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [query])

  const { data: allConvs = [] } = useQuery({
    queryKey: ['conversations'],
    queryFn: () => conversationsApi.list(),
    staleTime: 10_000,
  })

  const { data: searchResults } = useQuery({
    queryKey: ['conversations-search', debouncedQ],
    queryFn: () => conversationsApi.search(debouncedQ),
    enabled: debouncedQ.length > 0,
    staleTime: 5_000,
  })

  const convs = debouncedQ ? (searchResults ?? []) : allConvs
  const groups = groupConversations(convs)

  const handleSelect = (id: number) => {
    setActiveConversation(id)
    navigate('/chat')
  }

  return (
    <div className={styles.convPanel}>
      <div className={styles.searchRow}>
        <span className={styles.searchIcon} aria-hidden="true">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="13" height="13">
            <circle cx="6.5" cy="6.5" r="4.5" />
            <line x1="10" y1="10" x2="14" y2="14" strokeLinecap="round" />
          </svg>
        </span>
        <input
          className={styles.searchInput}
          type="search"
          placeholder="Search…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search conversations"
        />
        {query && (
          <button className={styles.searchClear} onClick={() => setQuery('')} aria-label="Clear search">✕</button>
        )}
      </div>

      <div className={styles.convList}>
        {groups.length === 0 && (
          <div className={styles.convEmpty}>
            {debouncedQ ? 'No results' : 'No conversations yet'}
          </div>
        )}
        {groups.map(([group, items]) => (
          <div key={group}>
            <div className={styles.groupLabel}>{group}</div>
            {items.map((c) => (
              <button
                key={c.id}
                className={`${styles.convItem} ${c.id === activeConversationId ? styles.convActive : ''}`}
                onClick={() => handleSelect(c.id)}
                title={c.title ?? `Conversation #${c.id}`}
              >
                <span className={styles.convTitle}>
                  {c.title ?? `conv #${c.id}`}
                </span>
                {c.tags.length > 0 && (
                  <span className={styles.tagRow}>
                    {c.tags.map((t) => (
                      <span key={t} className={styles.tagChip}>{t}</span>
                    ))}
                  </span>
                )}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <ul className={styles.navList} role="list">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                `${styles.navItem} ${isActive ? styles.active : ''}`
              }
            >
              <span className={styles.icon} aria-hidden="true">
                {ICONS[item.icon]}
              </span>
              <span className={styles.label}>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      <ConversationPanel />
    </nav>
  )
}
