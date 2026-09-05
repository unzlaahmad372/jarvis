import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from '@/app/stores/chatStore'

describe('chatStore', () => {
  beforeEach(() => {
    useChatStore.setState({
      activeConversationId: null,
      streamingContent: '',
      isStreaming: false,
      jarvisState: 'IDLE',
      lastError: null,
    })
  })

  it('starts in IDLE state', () => {
    const state = useChatStore.getState()
    expect(state.jarvisState).toBe('IDLE')
    expect(state.isStreaming).toBe(false)
    expect(state.activeConversationId).toBeNull()
  })

  it('startStreaming sets isStreaming and THINKING state', () => {
    useChatStore.getState().startStreaming()
    const state = useChatStore.getState()
    expect(state.isStreaming).toBe(true)
    expect(state.jarvisState).toBe('THINKING')
    expect(state.streamingContent).toBe('')
    expect(state.lastError).toBeNull()
  })

  it('appendStreamChunk accumulates content', () => {
    useChatStore.getState().startStreaming()
    useChatStore.getState().appendStreamChunk('Hello')
    useChatStore.getState().appendStreamChunk(' world')
    expect(useChatStore.getState().streamingContent).toBe('Hello world')
  })

  it('finishStreaming resets streaming state and sets conversation', () => {
    useChatStore.getState().startStreaming()
    useChatStore.getState().finishStreaming(42)
    const state = useChatStore.getState()
    expect(state.isStreaming).toBe(false)
    expect(state.streamingContent).toBe('')
    expect(state.jarvisState).toBe('IDLE')
    expect(state.activeConversationId).toBe(42)
  })

  it('setError sets error state and stops streaming', () => {
    useChatStore.getState().startStreaming()
    useChatStore.getState().setError('Something went wrong')
    const state = useChatStore.getState()
    expect(state.isStreaming).toBe(false)
    expect(state.jarvisState).toBe('ERROR')
    expect(state.lastError).toBe('Something went wrong')
  })

  it('clearError resets to IDLE', () => {
    useChatStore.getState().setError('oops')
    useChatStore.getState().clearError()
    const state = useChatStore.getState()
    expect(state.lastError).toBeNull()
    expect(state.jarvisState).toBe('IDLE')
  })

  it('setActiveConversation updates the active ID', () => {
    useChatStore.getState().setActiveConversation(7)
    expect(useChatStore.getState().activeConversationId).toBe(7)
  })
})
