import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchHealth } from '../api/client'
import { useAuthStore } from '../stores/authStore'

export function HealthPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 10_000,
  })
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  async function handleLogout(): Promise<void> {
    await logout()
    navigate('/login')
  }

  return (
    <main>
      <h1>Gas Station Wars</h1>
      {user && (
        <p>
          Signed in as {user.display_name} ({user.email}){' '}
          <button type="button" onClick={() => void handleLogout()}>
            Log out
          </button>
        </p>
      )}
      <h2>Backend health</h2>
      {isLoading && <p>Checking backend...</p>}
      {isError && <p role="alert">Backend unreachable: {String(error)}</p>}
      {data && (
        <ul>
          <li>Overall: {data.status}</li>
          <li>Database: {data.database}</li>
        </ul>
      )}
    </main>
  )
}
