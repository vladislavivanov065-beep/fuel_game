import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { joinGame, resolveInviteCode } from '../api/games'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

export function JoinGamePage() {
  const { inviteCode } = useParams<{ inviteCode: string }>()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [joining, setJoining] = useState(false)

  const {
    data: preview,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['invite', inviteCode],
    queryFn: () => resolveInviteCode(inviteCode ?? ''),
    enabled: Boolean(inviteCode),
    retry: false,
  })

  async function handleJoin(): Promise<void> {
    if (!preview || !inviteCode) {
      return
    }
    setJoining(true)
    setError(null)
    try {
      const game = await joinGame(preview.id, inviteCode)
      navigate(`/games/${game.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to join game')
    } finally {
      setJoining(false)
    }
  }

  return (
    <Card style={{ maxWidth: 420 }}>
      <h2>Присоединиться к игре</h2>
      {isLoading && <p>Загрузка приглашения...</p>}
      {isError && (
        <p role="alert" style={{ color: 'var(--danger)' }}>
          Код приглашения не найден.
        </p>
      )}
      {preview && (
        <>
          <p>
            {preview.name} — {preview.status} ({preview.player_count} игроков)
          </p>
          {error && (
            <p role="alert" style={{ color: 'var(--danger)' }}>
              {error}
            </p>
          )}
          <Button
            type="button"
            onClick={() => void handleJoin()}
            disabled={joining}
            style={{ marginTop: 12 }}
          >
            {joining ? 'Вход...' : 'Войти'}
          </Button>
        </>
      )}
    </Card>
  )
}
