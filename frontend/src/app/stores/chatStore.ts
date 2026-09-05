/**
 * chatStore — manages streaming state, active conversation, and pending messages.
 * Server-owned data (conversation list, history) lives in TanStack Query.
 */

import { create } from 'zustand'

export type JarvisState =
  | 'IDLE'
  | 'THINKING'
  | 'USING_TOOL'
  | 'WAITING_FOR_APPROVAL'
  | 'ERROR'
  | 'OFFLINE'

interface ChatStore {
  /** Currently active conversation ID (null = new conversation) */
  activeConversationId: number | null
  /** Streaming response text being built up */
  streamingContent: string
  /** Whether a request is in flight */
  isStreaming: boolean
  /** Current JARVIS core state */
  jarvisState: JarvisState
  /** Last error message */
  lastError: string | null

  setActiveConversation: (id: number | null) => void
  startStreaming: () => void
  appendStreamChunk: (chunk: string) => void
  finishStreaming: (conversationId: number) => void
  setError: (message: string) => void
  clearError: () => void
  setJarvisState: (state: JarvisState) => void
}

export const useChatStore = create<ChatStore>((set) => ({
  activeConversationId: null,
  streamingContent: '',
  isStreaming: false,
  jarvisState: 'IDLE',
  lastError: null,

  setActiveConversation: (id) => set({ activeConversationId: id }),

  startStreaming: () =>
    set({ isStreaming: true, streamingContent: '', jarvisState: 'THINKING', lastError: null }),

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
}))
