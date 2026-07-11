import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getGame, leaveGame, setReady, startGame } from '../api/games'
import { useAuthStore } from '../stores/authStore'
import { useGameSocket } from '../websocket/useGameSocket'

export function LobbyPage() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const {
    data: game,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['game', gameId],
    queryFn: () => getGame(gameId ?? ''),
    enabled: Boolean(gameId),
  })

  useGameSocket(gameId, () => {
    void queryClient.invalidateQueries({ queryKey: ['game', gameId] })
  })

  const me = game?.players.find((p) => p.user_id === user?.id)

  async function handleToggleReady(): Promise<void> {
    if (!gameId || !me) return
    setBusy(true)
    setError(null)
    try {
      await setReady(gameId, !me.is_ready)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update readiness')
    } finally {
      setBusy(false)
    }
  }

  async function handleStart(): Promise<void> {
    if (!gameId) return
    setBusy(true)
    setError(null)
    try {
      await startGame(gameId)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to start game')
    } finally {
      setBusy(false)
    }
  }

  async function handleLeave(): Promise<void> {
    if (!gameId) return
    setBusy(true)
    setError(null)
    try {
      await leaveGame(gameId)
      navigate('/')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to leave game')
    } finally {
      setBusy(false)
    }
  }

  if (isLoading) {
    return (
      <main>
        <p>Loading lobby...</p>
      </main>
    )
  }

  if (isError || !game) {
    return (
      <main>
        <p role="alert">Could not load this game.</p>
      </main>
    )
  }

  return (
    <main>
      <h1>{game.name}</h1>
      <p>
        Status: {game.status} | Invite code: <code>{game.invite_code}</code>
      </p>
      {error && <p role="alert">{error}</p>}

      <h2>Players</h2>
      <ul>
        {game.players.map((player) => (
          <li key={player.id}>
            {player.display_name}
            {player.is_admin ? ' (creator)' : ''} — {player.is_ready ? 'ready' : 'not ready'} —
            balance: {player.balance}
          </li>
        ))}
      </ul>

      {game.status === 'lobby' && me && (
        <button type="button" onClick={() => void handleToggleReady()} disabled={busy}>
          {me.is_ready ? 'Mark not ready' : 'Mark ready'}
        </button>
      )}

      {game.status === 'lobby' && me?.is_admin && (
        <button type="button" onClick={() => void handleStart()} disabled={busy}>
          Start game
        </button>
      )}

      {me && !me.is_admin && (
        <button type="button" onClick={() => void handleLeave()} disabled={busy}>
          Leave game
        </button>
      )}
    </main>
  )
}
