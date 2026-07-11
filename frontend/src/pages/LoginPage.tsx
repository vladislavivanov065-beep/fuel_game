import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

export function LoginPage() {
  const login = useAuthStore((s) => s.login)
  const error = useAuthStore((s) => s.error)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setSubmitting(true)
    try {
      await login({ email, password })
      navigate('/')
    } catch {
      // error already surfaced via the auth store
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main>
      <h1>Sign in</h1>
      <form onSubmit={(e) => void handleSubmit(e)}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
      <p>
        No account? <Link to="/register">Register</Link>
      </p>
    </main>
  )
}
