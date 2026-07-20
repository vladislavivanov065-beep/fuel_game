import type { ReactNode } from 'react'

export function Badge({
  children,
  tone = 'accent',
}: {
  children: ReactNode
  tone?: 'accent' | 'danger'
}) {
  const color = tone === 'danger' ? 'var(--danger)' : 'var(--accent-2)'
  const background = tone === 'danger' ? 'var(--danger-bg)' : 'var(--accent-bg)'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 12,
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
        color,
        background,
        borderRadius: 999,
        padding: '3px 10px',
      }}
    >
      {children}
    </span>
  )
}
