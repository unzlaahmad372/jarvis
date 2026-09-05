import { Outlet } from 'react-router-dom'
import { TopBar } from '@/components/layout/TopBar'
import { Sidebar } from '@/components/layout/Sidebar'
import { HealthStrip } from '@/components/layout/HealthStrip'
import styles from './App.module.css'

export function App() {
  return (
    <div className={styles.shell}>
      <TopBar />
      <div className={styles.body}>
        <Sidebar />
        <main className={styles.main} id="main-content">
          <Outlet />
        </main>
      </div>
      <HealthStrip />
    </div>
  )
}
