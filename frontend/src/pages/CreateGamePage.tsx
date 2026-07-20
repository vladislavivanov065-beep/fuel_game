import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createGame } from '../api/games'
import { ApiError } from '../api/client'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

export function CreateGamePage() {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const game = await createGame(name)
      navigate(`/games/${game.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create game')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card style={{ maxWidth: 420 }}>
      <h2>Новая игра</h2>
      <form
        onSubmit={(e) => void handleSubmit(e)}
        style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      >
        <label>
          Название игры
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
          />
        </label>
        {error && (
          <p role="alert" style={{ color: 'var(--danger)' }}>
            {error}
          </p>
        )}
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Создание...' : 'Создать игру'}
        </Button>
      </form>
    </Card>
  )
}
