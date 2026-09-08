/**
 * chatStore — manages streaming state, active conversation, and pending messages.
 * Server-owned data (conversation list, history) lives in TanStack Query.
 */

import { create } from 'zustand'
import type { CitationOut, ConfirmationOut, PlanStep } from '@/types/api'

export type JarvisState =
  | 'IDLE'
  | 'LISTENING'
  | 'THINKING'
  | 'USING_TOOL'
  | 'WAITING_FOR_APPROVAL'
  | 'ERROR'
  | 'OFFLINE'

export interface TokenUsageSummary {
  input: number | null
  output: number | null
  context: number | null
}

interface ChatStore {
  activeConversationId: number | null
  streamingContent: string
  isStreaming: boolean
  jarvisState: JarvisState
  lastError: string | null
  pendingConfirmation: ConfirmationOut | null
  pendingConfirmationMessage: string | null  // original message awaiting confirmation
  lastPlanSteps: PlanStep[]
  lastIntent: string | null
  lastCitations: CitationOut[]
  lastTokenUsage: TokenUsageSummary | null
  wakeWordEnabled: boolean

  setActiveConversation: (id: number | null) => void
  startStreaming: () => void
  appendStreamChunk: (chunk: string) => void
  finishStreaming: (conversationId: number) => void
  setError: (message: string) => void
  clearError: () => void
  setJarvisState: (state: JarvisState) => void
  setPendingConfirmation: (c: ConfirmationOut | null, originalMessage?: string) => void
  setLastPlanSteps: (steps: PlanStep[], intent: string) => void
  setLastCitations: (citations: CitationOut[]) => void
  setLastTokenUsage: (usage: TokenUsageSummary) => void
  toggleWakeWord: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  activeConversationId: null,
  streamingContent: '',
  isStreaming: false,
  jarvisState: 'IDLE',
  lastError: null,
  pendingConfirmation: null,
  pendingConfirmationMessage: null,
  lastPlanSteps: [],
  lastIntent: null,
  lastCitations: [],
  lastTokenUsage: null,
  wakeWordEnabled: false,

  setActiveConversation: (id) => set({ activeConversationId: id }),

  startStreaming: () =>
    set({
      isStreaming: true,
      streamingContent: '',
      jarvisState: 'THINKING',
      lastError: null,
      pendingConfirmation: null,
      pendingConfirmationMessage: null,
      lastPlanSteps: [],
      lastIntent: null,
      lastCitations: [],
      lastTokenUsage: null,
    }),

  appendStreamChunk: (chunk) =>
    set((s) => ({ streamingContent: s.streamingContent + chunk })),

  finishStreaming: (conversationId) =>
    set({
      isStreaming: false,
      streamingContent: '',
      jarvisState: 'IDLE',
      activeConversationId: conversationId,
    }),

  setError: (message) =>
    set({ isStreaming: false, jarvisState: 'ERROR', lastError: message }),

  clearError: () => set({ lastError: null, jarvisState: 'IDLE' }),

  setJarvisState: (state) => set({ jarvisState: state }),

  setPendingConfirmation: (c, originalMessage) =>
    set((s) => ({
      pendingConfirmation: c,
      pendingConfirmationMessage: originalMessage ?? (c ? s.pendingConfirmationMessage : null),
      jarvisState: c ? 'WAITING_FOR_APPROVAL' : 'IDLE',
    })),

  setLastPlanSteps: (steps, intent) =>
    set({ lastPlanSteps: steps, lastIntent: intent }),

  setLastCitations: (citations) => set({ lastCitations: citations }),

  setLastTokenUsage: (usage) => set({ lastTokenUsage: usage }),
  toggleWakeWord: () => set((s) => ({ wakeWordEnabled: !s.wakeWordEnabled })),
}))
