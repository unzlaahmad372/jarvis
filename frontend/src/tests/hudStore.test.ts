import { describe, it, expect, beforeEach } from 'vitest'
import { useHudStore } from '@/app/stores/hudStore'

describe('hudStore', () => {
  beforeEach(() => {
    useHudStore.setState({ mode: 'FOCUS', health: null, sidebarOpen: true })
  })

  it('defaults to FOCUS mode', () => {
    expect(useHudStore.getState().mode).toBe('FOCUS')
  })

  it('toggleMode switches between FOCUS and COMMAND_CENTER', () => {
    useHudStore.getState().toggleMode()
    expect(useHudStore.getState().mode).toBe('COMMAND_CENTER')
    useHudStore.getState().toggleMode()
    expect(useHudStore.getState().mode).toBe('FOCUS')
  })

  it('setMode sets mode directly', () => {
    useHudStore.getState().setMode('COMMAND_CENTER')
    expect(useHudStore.getState().mode).toBe('COMMAND_CENTER')
  })

  it('setHealth stores health data', () => {
    const health = {
      jarvis: 'READY' as const,
      dependencies: [{ name: 'database', status: 'healthy' as const, detail: null }],
    }
    useHudStore.getState().setHealth(health)
    expect(useHudStore.getState().health).toEqual(health)
  })
})
