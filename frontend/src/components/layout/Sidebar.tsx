import { NavLink } from 'react-router-dom'
import styles from './Sidebar.module.css'

const NAV_ITEMS = [
  { to: '/chat', label: 'Chat', icon: '💬' },
  { to: '/documents', label: 'Documents', icon: '📄' },
  { to: '/memory', label: 'Memory', icon: '🧠' },
  { to: '/tools', label: 'Tools', icon: '🔧' },
  { to: '/system', label: 'System', icon: '⚡' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
] as const

export function Sidebar() {
  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <ul className={styles.navList} role="list">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                `${styles.navItem} ${isActive ? styles.active : ''}`
              }
              aria-current={undefined}
            >
              <span className={styles.icon} aria-hidden="true">{item.icon}</span>
              <span className={styles.label}>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
