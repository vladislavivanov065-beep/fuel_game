import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { forgotPassword } from '../api/auth'
import { ApiError } from '../api/client'
import { AuthLayout } from '../components/layout/AuthLayout'
import { Button } from '../components/ui/Button'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resetLink, setResetLink] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const result = await forgotPassword(email)
      setSubmitted(true)
      if (result.reset_token) {
        const link = `${window.location.origin}/reset-password?token=${result.reset_token}`
        setResetLink(link)
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось запросить сброс пароля')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout>
      <h1 style={{ fontSize: 24, textAlign: 'center' }}>Восстановление пароля</h1>
      {!submitted && (
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
          {error && (
            <p role="alert" style={{ color: 'var(--danger)' }}>
              {error}
            </p>
          )}
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Отправка...' : 'Запросить сброс пароля'}
          </Button>
        </form>
      )}
      {submitted && (
        <div>
          <p>
            Если аккаунт с таким email существует, ниже — ссылка для сброса пароля.
            {/* Этап 15: отправка email не настроена — ссылка показывается прямо здесь. */}
          </p>
          {resetLink ? (
            <p style={{ wordBreak: 'break-all' }}>
              <Link to={`/reset-password?token=${new URL(resetLink).searchParams.get('token')}`}>
                {resetLink}
              </Link>
            </p>
          ) : (
            <p style={{ color: 'var(--text)' }}>
              Аккаунт с таким email не найден, но по соображениям безопасности мы всегда
              показываем это сообщение.
            </p>
          )}
        </div>
      )}
      <p style={{ textAlign: 'center', marginTop: 16 }}>
        <Link to="/login">Вернуться ко входу</Link>
      </p>
    </AuthLayout>
  )
}
