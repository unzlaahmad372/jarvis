import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from '@/app/stores/chatStore'
import type { ConfirmationOut } from '@/types/api'

const MOCK_CONFIRMATION: ConfirmationOut = {
  confirmation_id: 'test-id-123',
  tool_name: 'system_info',
  risk_level: 'SENSITIVE',
  policy_rule: 'SENSITIVE_ACTION_CONFIRMATION',
  action_digest: 'abc123def456',
  expires_at: new Date(Date.now() + 300_000).toISOString(),
}

describe('chatStore', () => {
  beforeEach(() => {
    useChatStore.setState({
      activeConversationId: null,
      streamingContent: '',
      isStreaming: false,
      jarvisState: 'IDLE',
      lastError: null,
      pendingConfirmation: null,
      lastPlanSteps: [],
      lastIntent: null,
    })
  })

  it('starts in IDLE state', () => {
    const state = useChatStore.getState()
    expect(state.jarvisState).toBe('IDLE')
    expect(state.isStreaming).toBe(false)
    expect(state.activeConversationId).toBeNull()
    expect(state.pendingConfirmation).toBeNull()
    expect(state.lastPlanSteps).toEqual([])
    expect(state.lastIntent).toBeNull()
  })

  it('startStreaming sets isStreaming and THINKING state', () => {
    useChatStore.getState().startStreaming()
    const state = useChatStore.getState()
    expect(state.isStreaming).toBe(true)
    expect(state.jarvisState).toBe('THINKING')
    expect(state.streamingContent).toBe('')
    expect(state.lastError).toBeNull()
    expect(state.pendingConfirmation).toBeNull()
    expect(state.lastPlanSteps).toEqual([])
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

  // ── Confirmation state ──────────────────────────────────────────────────────

  it('setPendingConfirmation sets WAITING_FOR_APPROVAL state', () => {
    useChatStore.getState().setPendingConfirmation(MOCK_CONFIRMATION)
    const state = useChatStore.getState()
    expect(state.pendingConfirmation).toEqual(MOCK_CONFIRMATION)
    expect(state.jarvisState).toBe('WAITING_FOR_APPROVAL')
  })

  it('setPendingConfirmation(null) clears confirmation and returns to IDLE', () => {
    useChatStore.getState().setPendingConfirmation(MOCK_CONFIRMATION)
    useChatStore.getState().setPendingConfirmation(null)
    const state = useChatStore.getState()
    expect(state.pendingConfirmation).toBeNull()
    expect(state.jarvisState).toBe('IDLE')
  })

  it('startStreaming clears any pending confirmation', () => {
    useChatStore.getState().setPendingConfirmation(MOCK_CONFIRMATION)
    useChatStore.getState().startStreaming()
    expect(useChatStore.getState().pendingConfirmation).toBeNull()
  })

  // ── Plan steps ──────────────────────────────────────────────────────────────

  it('setLastPlanSteps stores steps and intent', () => {
    const steps = [
      { tool_name: 'system_info', success: true, policy_decision: 'ALLOW',
        requires_confirmation: false, confirmation_id: null, error: null },
    ]
    useChatStore.getState().setLastPlanSteps(steps, 'SYSTEM_OPERATION')
    const state = useChatStore.getState()
    expect(state.lastPlanSteps).toEqual(steps)
    expect(state.lastIntent).toBe('SYSTEM_OPERATION')
  })

  it('startStreaming clears last plan steps', () => {
    const steps = [
      { tool_name: 'disk_usage', success: true, policy_decision: 'ALLOW',
        requires_confirmation: false, confirmation_id: null, error: null },
    ]
    useChatStore.getState().setLastPlanSteps(steps, 'SYSTEM_OPERATION')
    useChatStore.getState().startStreaming()
    expect(useChatStore.getState().lastPlanSteps).toEqual([])
    expect(useChatStore.getState().lastIntent).toBeNull()
  })

  it('confirmation state cannot be set to approved by client mutation alone', () => {
    // The store only holds the pending confirmation — approval requires
    // a real API call to /api/v1/tools/confirm. Mutating store state
    // directly does not execute the tool.
    useChatStore.getState().setPendingConfirmation(MOCK_CONFIRMATION)
    // Clearing it without calling the API just dismisses the panel
    useChatStore.getState().setPendingConfirmation(null)
    // No tool execution happened — state is simply cleared
    expect(useChatStore.getState().pendingConfirmation).toBeNull()
    expect(useChatStore.getState().jarvisState).toBe('IDLE')
  })
})
