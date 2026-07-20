import { useNavigate, Outlet } from 'react-router-dom'
import { Button } from '../ui/Button'
import { useAuthStore } from '../../stores/authStore'

export function AppLayout() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  async function handleLogout(): Promise<void> {
    await logout()
    navigate('/login')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100svh' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 24px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--surface)',
        }}
      >
        <a
          href="/"
          style={{
            color: 'var(--text-h)',
            fontWeight: 700,
            fontSize: 18,
            textDecoration: 'none',
          }}
        >
          ⛽ Войны заправок
        </a>
        {user && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ color: 'var(--text)' }}>{user.display_name}</span>
            <Button variant="secondary" onClick={() => void handleLogout()}>
              Выйти
            </Button>
          </div>
        )}
      </header>
      <main style={{ flex: 1, width: '100%', maxWidth: 1200, margin: '0 auto', padding: 24 }}>
        <Outlet />
      </main>
    </div>
  )
}
