import { useEffect, useRef } from 'react'
import { API_BASE_URL } from '../api/client'

export interface GameEvent {
  event: string
  event_id: string
  server_time: string
  game_id: string
  data: Record<string, unknown>
}

export function useGameSocket(gameId: string | undefined, onEvent: (event: GameEvent) => void) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!gameId) {
      return
    }

    const wsUrl = `${API_BASE_URL.replace(/^http/, 'ws')}/ws/games/${gameId}`
    const socket = new WebSocket(wsUrl)

    socket.onmessage = (message: MessageEvent<string>) => {
      const parsed = JSON.parse(message.data) as GameEvent
      onEventRef.current(parsed)
    }

    return () => {
      socket.close()
    }
  }, [gameId])
}
