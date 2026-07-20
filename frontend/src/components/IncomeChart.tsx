import { useId, useMemo, useState } from 'react'
import type { FinancialTransaction } from '../api/finance'
import { Card } from './ui/Card'

interface IncomeChartProps {
  transactions: FinancialTransaction[]
}

const WIDTH = 640
const HEIGHT = 220
const PADDING_LEFT = 64
const PADDING_RIGHT = 16
const PADDING_TOP = 16
const PADDING_BOTTOM = 28

function formatMoney(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function IncomeChart({ transactions }: IncomeChartProps) {
  const gradientId = useId()
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const [showTable, setShowTable] = useState(false)

  const points = useMemo(
    () =>
      transactions.map((tx) => ({
        time: new Date(tx.created_at).getTime(),
        balance: Number(tx.balance_after),
        tx,
      })),
    [transactions],
  )

  if (points.length === 0) {
    return (
      <Card>
        <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>Доход</h3>
        <p style={{ color: 'var(--text)', fontSize: 14 }}>
          Пока нет финансовых операций. График появится после первых продаж.
        </p>
      </Card>
    )
  }

  const minBalance = Math.min(...points.map((p) => p.balance))
  const maxBalance = Math.max(...points.map((p) => p.balance))
  const minTime = points[0].time
  const maxTime = points[points.length - 1].time
  const balanceRange = maxBalance - minBalance || 1
  const timeRange = maxTime - minTime || 1

  const plotWidth = WIDTH - PADDING_LEFT - PADDING_RIGHT
  const plotHeight = HEIGHT - PADDING_TOP - PADDING_BOTTOM

  function xFor(time: number): number {
    return PADDING_LEFT + ((time - minTime) / timeRange) * plotWidth
  }

  function yFor(balance: number): number {
    return PADDING_TOP + plotHeight - ((balance - minBalance) / balanceRange) * plotHeight
  }

  const linePath = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xFor(p.time).toFixed(1)} ${yFor(p.balance).toFixed(1)}`)
    .join(' ')

  const areaPath =
    `${linePath} ` +
    `L ${xFor(points[points.length - 1].time).toFixed(1)} ${(PADDING_TOP + plotHeight).toFixed(1)} ` +
    `L ${xFor(points[0].time).toFixed(1)} ${(PADDING_TOP + plotHeight).toFixed(1)} Z`

  const gridLines = 4
  const gridValues = Array.from({ length: gridLines + 1 }, (_, i) => minBalance + (balanceRange * i) / gridLines)

  const hovered = hoverIndex !== null ? points[hoverIndex] : null
  const latest = points[points.length - 1]

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h3 style={{ margin: '0 0 8px', fontSize: 16, color: 'var(--text-h)' }}>Доход</h3>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          style={{ fontSize: 12 }}
        >
          {showTable ? 'Показать график' : 'Показать таблицу'}
        </button>
      </div>

      {showTable ? (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Время</th>
                <th style={{ textAlign: 'left', padding: 4 }}>Тип</th>
                <th style={{ textAlign: 'right', padding: 4 }}>Сумма</th>
                <th style={{ textAlign: 'right', padding: 4 }}>Баланс</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => (
                <tr key={tx.id}>
                  <td style={{ padding: 4 }}>{formatTime(tx.created_at)}</td>
                  <td style={{ padding: 4 }}>{tx.transaction_type}</td>
                  <td style={{ padding: 4, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {formatMoney(Number(tx.amount))}
                  </td>
                  <td style={{ padding: 4, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {formatMoney(Number(tx.balance_after))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            style={{ width: '100%', height: 'auto', display: 'block' }}
            role="img"
            aria-label={`Баланс изменился с ${formatMoney(points[0].balance)} до ${formatMoney(latest.balance)}`}
          >
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent-2)" stopOpacity="0.25" />
                <stop offset="100%" stopColor="var(--accent-2)" stopOpacity="0" />
              </linearGradient>
            </defs>

            {gridValues.map((value) => (
              <g key={value}>
                <line
                  x1={PADDING_LEFT}
                  x2={WIDTH - PADDING_RIGHT}
                  y1={yFor(value)}
                  y2={yFor(value)}
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                <text
                  x={PADDING_LEFT - 8}
                  y={yFor(value)}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fontSize={11}
                  fill="var(--text)"
                >
                  {formatMoney(value)}
                </text>
              </g>
            ))}

            <line
              x1={PADDING_LEFT}
              x2={WIDTH - PADDING_RIGHT}
              y1={PADDING_TOP + plotHeight}
              y2={PADDING_TOP + plotHeight}
              stroke="var(--border)"
              strokeWidth={1}
            />

            <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
            <path d={linePath} fill="none" stroke="var(--accent-2)" strokeWidth={2} strokeLinejoin="round" />

            <circle
              cx={xFor(latest.time)}
              cy={yFor(latest.balance)}
              r={4}
              fill="var(--accent-2)"
            />

            {hovered && (
              <>
                <line
                  x1={xFor(hovered.time)}
                  x2={xFor(hovered.time)}
                  y1={PADDING_TOP}
                  y2={PADDING_TOP + plotHeight}
                  stroke="var(--border)"
                  strokeWidth={1}
                  strokeDasharray="3 3"
                />
                <circle
                  cx={xFor(hovered.time)}
                  cy={yFor(hovered.balance)}
                  r={4}
                  fill="var(--surface)"
                  stroke="var(--accent-2)"
                  strokeWidth={2}
                />
              </>
            )}

            {points.map((p, i) => (
              <rect
                key={p.tx.id}
                x={xFor(p.time) - (plotWidth / points.length / 2 || 4)}
                y={PADDING_TOP}
                width={Math.max(plotWidth / points.length, 8)}
                height={plotHeight}
                fill="transparent"
                onMouseEnter={() => setHoverIndex(i)}
                onMouseLeave={() => setHoverIndex((current) => (current === i ? null : current))}
              />
            ))}
          </svg>

          <div style={{ fontSize: 13, color: 'var(--text)', minHeight: 20 }}>
            {hovered ? (
              <span>
                {formatTime(hovered.tx.created_at)} — {hovered.tx.transaction_type}:{' '}
                <strong style={{ color: 'var(--text-h)' }}>{formatMoney(hovered.balance)}</strong>
              </span>
            ) : (
              <span>
                Текущий баланс:{' '}
                <strong style={{ color: 'var(--text-h)' }}>{formatMoney(latest.balance)}</strong>
              </span>
            )}
          </div>
        </>
      )}
    </Card>
  )
}
