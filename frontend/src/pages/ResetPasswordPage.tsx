import { type FormEvent, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { resetPassword } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthLayout } from '../components/layout/AuthLayout'
import { Button } from '../components/ui/Button'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const navigate = useNavigate()
  const [newPassword, setNewPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await resetPassword(token, newPassword)
      setDone(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сбросить пароль')
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <AuthLayout>
        <p role="alert" style={{ color: 'var(--danger)' }}>
          Ссылка для сброса пароля недействительна.
        </p>
        <p style={{ textAlign: 'center', marginTop: 16 }}>
          <Link to="/forgot-password">Запросить новую ссылку</Link>
        </p>
      </AuthLayout>
    )
  }

  if (done) {
    return (
      <AuthLayout>
        <p>Пароль изменён. Все предыдущие сеансы выхода из системы завершены.</p>
        <Button style={{ marginTop: 12 }} onClick={() => navigate('/login')}>
          Войти с новым паролем
        </Button>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <h1 style={{ fontSize: 24, textAlign: 'center' }}>Новый пароль</h1>
      <form
        onSubmit={(e) => void handleSubmit(e)}
        style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      >
        <label>
          Новый пароль
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
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
          {submitting ? 'Сохранение...' : 'Сохранить новый пароль'}
        </Button>
      </form>
    </AuthLayout>
  )
}
