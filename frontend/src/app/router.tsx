import { createBrowserRouter, Navigate } from 'react-router-dom'
import { App } from './App'
import { ChatPage } from '@/features/chat/ChatPage'
import { DocumentsPage } from '@/features/documents/DocumentsPage'
import { MemoryPage } from '@/features/memory/MemoryPage'
import { OperationsPage } from '@/features/operations/OperationsPage'
import { SystemPage } from '@/features/system/SystemPage'
import { ToolsPage } from '@/features/tools/ToolsPage'
import { KubernetesPage } from '@/features/kubernetes/KubernetesPage'
import { AutomationsPage } from '@/features/automation/AutomationsPage'
import { BackupPage } from '@/features/backup/BackupPage'
import { AuthPage } from '@/features/auth/AuthPage'
import { AuditPage } from '@/features/audit/AuditPage'
import { MCPPage } from '@/features/mcp/MCPPage'
import { ObservabilityPage } from '@/features/observability/ObservabilityPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'documents', element: <DocumentsPage /> },
      { path: 'memory', element: <MemoryPage /> },
      { path: 'tools', element: <ToolsPage /> },
      { path: 'kubernetes', element: <KubernetesPage /> },
      { path: 'operations', element: <OperationsPage /> },
      { path: 'automations', element: <AutomationsPage /> },
      { path: 'backup', element: <BackupPage /> },
      { path: 'auth', element: <AuthPage /> },
      { path: 'audit', element: <AuditPage /> },
      { path: 'mcp', element: <MCPPage /> },
      { path: 'observability', element: <ObservabilityPage /> },
      { path: 'system', element: <SystemPage /> },
      {
        path: 'settings',
        element: (
          <div style={{ padding: 24, color: 'var(--hud-text-secondary)', fontFamily: 'var(--hud-font-mono)' }}>
            Settings — coming in a future phase
          </div>
        ),
      },
    ],
  },
])
