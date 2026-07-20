import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthLayout } from '../components/layout/AuthLayout'
import { Button } from '../components/ui/Button'
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
    <AuthLayout>
      <h1 style={{ fontSize: 24, textAlign: 'center' }}>Вход</h1>
      <form
        onSubmit={(e) => void handleSubmit(e)}
        style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      >
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
          Пароль
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <p role="alert" style={{ color: 'var(--danger)' }}>
            {error}
          </p>
        )}
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Вход...' : 'Войти'}
        </Button>
      </form>
      <p style={{ textAlign: 'center', marginTop: 16 }}>
        <Link to="/forgot-password">Забыли пароль?</Link>
      </p>
      <p style={{ textAlign: 'center', marginTop: 8 }}>
        Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
      </p>
    </AuthLayout>
  )
}
