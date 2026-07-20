import type { CSSProperties, ReactNode } from 'react'

export function Card({
  children,
  style,
}: {
  children: ReactNode
  style?: CSSProperties
}) {
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-card)',
        padding: 20,
        ...style,
      }}
    >
      {children}
    </div>
  )
}
