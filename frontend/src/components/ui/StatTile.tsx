export function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 16px',
        minWidth: 140,
      }}
    >
      <div style={{ fontSize: 12, color: 'var(--text)' }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-h)' }}>{value}</div>
    </div>
  )
}
