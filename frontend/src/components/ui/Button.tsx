import type { ButtonHTMLAttributes, CSSProperties } from 'react'

type Variant = 'primary' | 'secondary' | 'danger'

const VARIANT_STYLE: Record<Variant, CSSProperties> = {
  primary: {
    background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
    color: '#0e1016',
    border: 'none',
  },
  secondary: {
    background: 'transparent',
    color: 'var(--text-h)',
    border: '1px solid var(--border)',
  },
  danger: {
    background: 'var(--danger-bg)',
    color: 'var(--danger)',
    border: '1px solid var(--danger)',
  },
}

export function Button({
  variant = 'primary',
  style,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      style={{
        font: 'inherit',
        fontWeight: 600,
        borderRadius: 'var(--radius-sm)',
        padding: '9px 16px',
        cursor: props.disabled ? 'not-allowed' : 'pointer',
        opacity: props.disabled ? 0.6 : 1,
        ...VARIANT_STYLE[variant],
        ...style,
      }}
    />
  )
}
