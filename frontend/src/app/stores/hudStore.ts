/**
 * hudStore — manages HUD mode, health summary, and global UI state.
 */

import { create } from 'zustand'
import type { DependenciesResponse } from '@/types/api'

export type HudMode = 'COMMAND_CENTER' | 'FOCUS'

interface HudStore {
  mode: HudMode
  health: DependenciesResponse | null
  sidebarOpen: boolean

  setMode: (mode: HudMode) => void
  toggleMode: () => void
  setHealth: (health: DependenciesResponse) => void
  setSidebarOpen: (open: boolean) => void
}

export const useHudStore = create<HudStore>((set) => ({
  mode: 'FOCUS',
  health: null,
  sidebarOpen: true,

  setMode: (mode) => set({ mode }),
  toggleMode: () =>
    set((s) => ({ mode: s.mode === 'FOCUS' ? 'COMMAND_CENTER' : 'FOCUS' })),
  setHealth: (health) => set({ health }),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
}))
