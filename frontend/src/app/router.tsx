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
import { SettingsPage } from '@/features/settings/SettingsPage'
import { ExportPage } from '@/features/export/ExportPage'
import { WorkspacePage } from '@/features/workspace/WorkspacePage'
import { NotificationsPage } from '@/features/notifications/NotificationsPage'
import { PluginsPage } from '@/features/plugins/PluginsPage'

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
      { path: 'settings', element: <SettingsPage /> },
      { path: 'export', element: <ExportPage /> },
      { path: 'workspace', element: <WorkspacePage /> },
      { path: 'notifications', element: <NotificationsPage /> },
      { path: 'plugins', element: <PluginsPage /> },
    ],
  },
])
