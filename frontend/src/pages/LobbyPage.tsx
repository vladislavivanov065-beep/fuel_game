import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getGame, leaveGame, setNetwork, setReady, startGame } from '../api/games'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { StatTile } from '../components/ui/StatTile'
import { useAuthStore } from '../stores/authStore'
import { useGameSocket } from '../websocket/useGameSocket'

export function LobbyPage() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [networkName, setNetworkName] = useState('')
  const [networkColor, setNetworkColor] = useState('#3366ff')

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

  async function handleSetNetwork(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!gameId) return
    setBusy(true)
    setError(null)
    try {
      await setNetwork(gameId, networkName, networkColor)
      await queryClient.invalidateQueries({ queryKey: ['game', gameId] })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to set network name')
    } finally {
      setBusy(false)
    }
  }

  if (isLoading) {
    return <Card>Загрузка лобби...</Card>
  }

  if (isError || !game) {
    return (
      <Card>
        <p role="alert" style={{ color: 'var(--danger)' }}>
          Не удалось загрузить игру.
        </p>
      </Card>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>{game.name}</h2>
          <span style={{ color: 'var(--text)' }}>
            {game.status} | Код: <code>{game.invite_code}</code>
          </span>
        </div>
        {error && (
          <p role="alert" style={{ color: 'var(--danger)' }}>
            {error}
          </p>
        )}
        {me && (
          <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
            <StatTile
              label="Баланс"
              value={`${Number(me.balance).toLocaleString('ru-RU')} ₽`}
            />
            <StatTile
              label="Net worth"
              value={`${Number(me.net_worth).toLocaleString('ru-RU')} ₽`}
            />
          </div>
        )}
      </Card>

      <Card>
        <h2>Игроки</h2>
        <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {game.players.map((player) => (
            <li
              key={player.id}
              style={{ padding: '8px 0', borderTop: '1px solid var(--border)' }}
            >
              <span style={{ color: 'var(--text-h)' }}>{player.display_name}</span>
              {player.is_admin && <Badge>Admin</Badge>}
              {' — '}
              {player.is_ready ? 'готов' : 'не готов'} —{' '}
              {Number(player.balance).toLocaleString('ru-RU')} ₽
              {player.network_name && (
                <>
                  {' — сеть: '}
                  <span style={{ color: player.network_color ?? undefined }}>
                    {player.network_name}
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      </Card>

      {me && (
        <Card>
          <h2>Ваша сеть</h2>
          <form
            onSubmit={(e) => void handleSetNetwork(e)}
            style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}
          >
            <label style={{ flex: 1, minWidth: 160 }}>
              Название
              <input
                type="text"
                value={networkName}
                onChange={(e) => setNetworkName(e.target.value)}
                placeholder={me.network_name ?? 'Network name'}
                required
                maxLength={64}
              />
            </label>
            <label>
              Цвет
              <input
                type="color"
                value={networkColor}
                onChange={(e) => setNetworkColor(e.target.value)}
              />
            </label>
            <Button type="submit" variant="secondary" disabled={busy}>
              Сохранить
            </Button>
          </form>
        </Card>
      )}

      <Card>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {game.status === 'lobby' && me && (
            <Button type="button" onClick={() => void handleToggleReady()} disabled={busy}>
              {me.is_ready ? 'Отметить не готов' : 'Отметить готов'}
            </Button>
          )}

          {game.status === 'lobby' && me?.is_admin && (
            <Button type="button" onClick={() => void handleStart()} disabled={busy}>
              Начать игру
            </Button>
          )}

          {game.status === 'running' && (
            <Link to={`/games/${gameId}/map`}>
              <Button type="button" variant="primary">
                Открыть карту игры
              </Button>
            </Link>
          )}

          {me && !me.is_admin && (
            <Button type="button" variant="danger" onClick={() => void handleLeave()} disabled={busy}>
              Покинуть игру
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}
