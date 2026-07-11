import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

export function ProtectedRoute() {
  const status = useAuthStore((s) => s.status)
  const checkSession = useAuthStore((s) => s.checkSession)

  useEffect(() => {
    if (status === 'idle') {
      void checkSession()
    }
  }, [status, checkSession])

  if (status === 'idle' || status === 'loading') {
    return <p>Loading...</p>
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
