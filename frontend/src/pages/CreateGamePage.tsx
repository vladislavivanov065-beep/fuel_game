import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createGame } from '../api/games'
import { ApiError } from '../api/client'

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
    <main>
      <h1>Create a new game</h1>
      <form onSubmit={(e) => void handleSubmit(e)}>
        <label>
          Game name
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Creating...' : 'Create game'}
        </button>
      </form>
    </main>
  )
}
