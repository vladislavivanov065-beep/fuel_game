import type { ReactNode } from 'react'
import { Card } from '../ui/Card'

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        minHeight: '100svh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg)',
      }}
    >
      <div style={{ width: 380, maxWidth: '90vw' }}>
        <Card>{children}</Card>
      </div>
    </div>
  )
}
