import type { GamePlayer } from '../api/games'

export function GameResultsPanel({
  players,
  finishedAt,
}: {
  players: GamePlayer[]
  finishedAt: string | null
}) {
  const ranked = [...players].sort((a, b) => Number(b.net_worth) - Number(a.net_worth))

  return (
    <div
      style={{
        border: '2px solid #d4af37',
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
        background: 'var(--surface, rgba(212, 175, 55, 0.05))',
      }}
    >
      <h2 style={{ margin: '0 0 4px', fontSize: 20 }}>Игра завершена</h2>
      {finishedAt && (
        <p style={{ fontSize: 12, color: 'var(--text-secondary, #666)', margin: '0 0 12px' }}>
          Завершена: {new Date(finishedAt).toLocaleString()}
        </p>
      )}
      <ol style={{ margin: 0, paddingLeft: 24 }}>
        {ranked.map((player, index) => (
          <li
            key={player.id}
            style={{
              fontSize: index === 0 ? 18 : 14,
              fontWeight: index === 0 ? 700 : 400,
              marginBottom: 6,
            }}
          >
            {player.display_name}
            {player.network_name && (
              <span style={{ color: player.network_color ?? undefined }}>
                {' '}
                ({player.network_name})
              </span>
            )}
            {' — '}
            {Number(player.net_worth).toLocaleString('ru-RU')} ₽
            {index === 0 && ' (победитель)'}
          </li>
        ))}
      </ol>
    </div>
  )
}
