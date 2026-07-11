import { useQuery } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listGames } from '../api/games'
import { useAuthStore } from '../stores/authStore'

export function GamesListPage() {
  const { data: games, isLoading } = useQuery({ queryKey: ['games'], queryFn: listGames })
  const [inviteCode, setInviteCode] = useState('')
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  function handleJoinSubmit(event: FormEvent): void {
    event.preventDefault()
    if (inviteCode.trim()) {
      navigate(`/join/${inviteCode.trim()}`)
    }
  }

  async function handleLogout(): Promise<void> {
    await logout()
    navigate('/login')
  }

  return (
    <main>
      <h1>Gas Station Wars</h1>
      {user && (
        <p>
          {user.display_name} ({user.email}){' '}
          <button type="button" onClick={() => void handleLogout()}>
            Log out
          </button>
        </p>
      )}

      <h2>Your games</h2>
      {isLoading && <p>Loading...</p>}
      {games && games.length === 0 && <p>You have no games yet.</p>}
      {games && games.length > 0 && (
        <ul>
          {games.map((game) => (
            <li key={game.id}>
              <Link to={`/games/${game.id}`}>{game.name}</Link> — {game.status} (
              {game.player_count} players)
            </li>
          ))}
        </ul>
      )}

      <p>
        <Link to="/games/new">Create a new game</Link>
      </p>
      <p>
        <Link to="/map">View the map</Link>
      </p>

      <h2>Join a game</h2>
      <form onSubmit={handleJoinSubmit}>
        <label>
          Invite code
          <input
            type="text"
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
            required
          />
        </label>
        <button type="submit">Join</button>
      </form>
    </main>
  )
}
