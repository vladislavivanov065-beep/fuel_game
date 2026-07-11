import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { joinGame, resolveInviteCode } from '../api/games'

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
    <main>
      <h1>Join game</h1>
      {isLoading && <p>Loading invite...</p>}
      {isError && <p role="alert">Invite code not found.</p>}
      {preview && (
        <>
          <p>
            {preview.name} — {preview.status} ({preview.player_count} players)
          </p>
          {error && <p role="alert">{error}</p>}
          <button type="button" onClick={() => void handleJoin()} disabled={joining}>
            {joining ? 'Joining...' : 'Join'}
          </button>
        </>
      )}
    </main>
  )
}
