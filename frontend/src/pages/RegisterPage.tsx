import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthLayout } from '../components/layout/AuthLayout'
import { Button } from '../components/ui/Button'
import { useAuthStore } from '../stores/authStore'

export function RegisterPage() {
  const register = useAuthStore((s) => s.register)
  const error = useAuthStore((s) => s.error)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setSubmitting(true)
    try {
      await register({ email, password, display_name: displayName })
      navigate('/')
    } catch {
      // error already surfaced via the auth store
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout>
      <h1 style={{ fontSize: 24, textAlign: 'center' }}>Регистрация</h1>
      <form
        onSubmit={(e) => void handleSubmit(e)}
        style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      >
        <label>
          Имя
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
          />
        </label>
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
            minLength={8}
            required
          />
        </label>
        {error && (
          <p role="alert" style={{ color: 'var(--danger)' }}>
            {error}
          </p>
        )}
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Создание аккаунта...' : 'Зарегистрироваться'}
        </Button>
      </form>
      <p style={{ textAlign: 'center', marginTop: 16 }}>
        Уже есть аккаунт? <Link to="/login">Войти</Link>
      </p>
    </AuthLayout>
  )
}
