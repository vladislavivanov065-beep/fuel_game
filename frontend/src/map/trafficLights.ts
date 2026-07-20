import type { TrafficLight } from '../api/map'

export type LightState = 'red' | 'yellow' | 'green'

export function lightStateAt(light: TrafficLight, nowMs: number): LightState {
  const cycleLength = light.red_seconds + light.yellow_seconds + light.green_seconds
  if (cycleLength <= 0) return 'green'

  const nowSeconds = nowMs / 1000
  const phase = ((nowSeconds + light.offset_seconds) % cycleLength + cycleLength) % cycleLength

  if (phase < light.red_seconds) return 'red'
  if (phase < light.red_seconds + light.yellow_seconds) return 'yellow'
  return 'green'
}

export const LIGHT_STATE_COLORS: Record<LightState, string> = {
  red: '#e53935',
  yellow: '#fdd835',
  green: '#43a047',
}
