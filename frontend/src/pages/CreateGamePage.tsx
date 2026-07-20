import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createGame } from '../api/games'
import { ApiError } from '../api/client'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

const DEFAULT_VEHICLE_SPAWN_PER_MINUTE = 20

export function CreateGamePage() {
  const [name, setName] = useState('')
  const [vehicleSpawnPerMinute, setVehicleSpawnPerMinute] = useState(
    DEFAULT_VEHICLE_SPAWN_PER_MINUTE,
  )
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const game = await createGame(name, {
        vehicle_spawn_per_minute: vehicleSpawnPerMinute,
      })
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
        <label>
          Интенсивность трафика: {vehicleSpawnPerMinute} машин/мин
          <input
            type="range"
            min={0}
            max={60}
            step={1}
            value={vehicleSpawnPerMinute}
            onChange={(e) => setVehicleSpawnPerMinute(Number(e.target.value))}
            style={{ width: '100%' }}
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
