import { create } from 'zustand'
import { invoke } from '@/lib/tauri'
type LaunchStatus = { running: boolean; client_path: string }
type Launcher = {
  running: boolean; busy: boolean; error: string
  refresh: () => Promise<void>
  launch: () => Promise<void>
}
export const useLauncherStore = create<Launcher>((set, get) => ({
  running: false, busy: false, error: '',
  refresh: async () => {
    if (get().busy) return
    try { const s = await invoke<LaunchStatus>('get_game_launch_status'); if (!get().busy) set({ running: s.running }) } catch { /* preview / shutting down */ }
  },
  launch: async () => {
    if (get().busy) return
    set({ busy: true, error: '' })
    try { const s = await invoke<LaunchStatus>('launch_game'); set({ running: s.running }) }
    catch (e) { set({ error: String(e) }) }
    finally { set({ busy: false }) }
  },
}))
