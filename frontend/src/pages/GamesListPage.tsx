import { useQuery } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listGames } from '../api/games'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

export function GamesListPage() {
  const { data: games, isLoading } = useQuery({ queryKey: ['games'], queryFn: listGames })
  const [inviteCode, setInviteCode] = useState('')
  const navigate = useNavigate()

  function handleJoinSubmit(event: FormEvent): void {
    event.preventDefault()
    if (inviteCode.trim()) {
      navigate(`/join/${inviteCode.trim()}`)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>Ваши игры</h2>
          <Link to="/games/new">
            <Button variant="primary">Создать игру</Button>
          </Link>
        </div>
        {isLoading && <p>Загрузка...</p>}
        {games && games.length === 0 && <p>У вас пока нет игр.</p>}
        {games && games.length > 0 && (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, marginTop: 12 }}>
            {games.map((game) => (
              <li
                key={game.id}
                style={{
                  padding: '10px 0',
                  borderTop: '1px solid var(--border)',
                }}
              >
                <Link to={`/games/${game.id}`} style={{ color: 'var(--text-h)' }}>
                  {game.name}
                </Link>{' '}
                <span style={{ color: 'var(--text)' }}>
                  — {game.status} ({game.player_count} игроков)
                </span>
              </li>
            ))}
          </ul>
        )}
        <p style={{ marginTop: 12 }}>
          <Link to="/map">Посмотреть карту</Link>
        </p>
      </Card>

      <Card>
        <h2>Присоединиться по коду</h2>
        <form
          onSubmit={handleJoinSubmit}
          style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}
        >
          <label style={{ flex: 1 }}>
            Код приглашения
            <input
              type="text"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              required
            />
          </label>
          <Button type="submit" variant="secondary">
            Войти
          </Button>
        </form>
      </Card>
    </div>
  )
}
