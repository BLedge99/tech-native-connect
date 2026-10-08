/** One WebSocket per page, shared.
 *
 * Previously each component called useWebSocket() independently — the bell, the
 * toast stack and the chat each opened their own socket. Three sockets per page
 * means three handshakes, three reconnect loops, and a chat socket that can lose
 * the race and never subscribe. Message delivery then silently fails.
 *
 * The provider owns the socket. Components subscribe to events instead.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

export type SocketStatus = 'connecting' | 'open' | 'closed'

export interface SocketFrame {
  type: string
  data?: Record<string, unknown>
  code?: string
  message?: string
  thread_id?: string
}

type MessageListener = (frame: SocketFrame) => void
type StatusListener = (status: SocketStatus) => void

interface WebSocketValue {
  status: SocketStatus
  subscribe: (threadId: string) => void
  unsubscribe: (threadId: string) => void
  send: (payload: Record<string, unknown>) => boolean
  /** Register a listener for `message` and `ack` frames. Returns an unsubscribe. */
  onMessage: (listener: MessageListener) => () => void
  /** Register a listener for `notification` frames. */
  onNotification: (listener: MessageListener) => () => void
}

const WebSocketContext = createContext<WebSocketValue | null>(null)

export function useSocket(): WebSocketValue {
  const ctx = useContext(WebSocketContext)
  if (!ctx) throw new Error('useSocket must be used inside <WebSocketProvider>')
  return ctx
}

const RECONNECT_STEPS_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000]

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SocketStatus>('connecting')
  const socketRef = useRef<WebSocket | null>(null)
  const attempts = useRef(0)
  const timerRef = useRef<number | null>(null)
  const stopped = useRef(false)

  const messageListeners = useRef(new Set<MessageListener>())
  const notificationListeners = useRef(new Set<MessageListener>())
  const statusListeners = useRef(new Set<StatusListener>())
  // Threads this page wants frames for. Re-sent on every (re)connect.
  const wanted = useRef(new Set<string>())

  const emitStatus = useCallback((next: SocketStatus) => {
    setStatus(next)
    for (const listener of statusListeners.current) listener(next)
  }, [])

  const send = useCallback((payload: Record<string, unknown>): boolean => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload))
      return true
    }
    return false
  }, [])

  const connect = useCallback(() => {
    if (stopped.current) return
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    // Same-origin path. Never hardcode a host.
    const socket = new WebSocket(`${proto}://${window.location.host}/api/v1/ws`)
    socketRef.current = socket

    socket.onopen = () => {
      attempts.current = 0
      emitStatus('open')
      // Re-subscribe after a reconnect: the server holds nothing for us.
      for (const threadId of wanted.current) {
        socket.send(JSON.stringify({ type: 'subscribe', thread_id: threadId }))
      }
    }

    socket.onmessage = (event) => {
      let frame: SocketFrame
      try {
        frame = JSON.parse(event.data as string) as SocketFrame
      } catch {
        return // a malformed frame must not kill the socket
      }
      if (frame.type === 'message' || frame.type === 'ack') {
        for (const listener of messageListeners.current) listener(frame)
      } else if (frame.type === 'notification') {
        for (const listener of notificationListeners.current) listener(frame)
      }
    }

    socket.onclose = () => {
      socketRef.current = null
      emitStatus('closed')
      if (stopped.current) return
      // Exponential backoff, capped, with jitter. Retry indefinitely — this is a
      // demo and giving up is worse than retrying.
      const step = RECONNECT_STEPS_MS[Math.min(attempts.current, RECONNECT_STEPS_MS.length - 1)]
      attempts.current += 1
      const delay = step + Math.random() * 500
      timerRef.current = window.setTimeout(connect, delay)
    }

    socket.onerror = () => socket.close()
  }, [emitStatus])

  useEffect(() => {
    stopped.current = false
    connect()
    return () => {
      stopped.current = true
      if (timerRef.current) window.clearTimeout(timerRef.current)
      socketRef.current?.close()
    }
  }, [connect])

  const subscribe = useCallback(
    (threadId: string) => {
      wanted.current.add(threadId)
      send({ type: 'subscribe', thread_id: threadId })
    },
    [send],
  )

  const unsubscribe = useCallback(
    (threadId: string) => {
      wanted.current.delete(threadId)
      send({ type: 'unsubscribe', thread_id: threadId })
    },
    [send],
  )

  const onMessage = useCallback((listener: MessageListener) => {
    messageListeners.current.add(listener)
    return () => messageListeners.current.delete(listener)
  }, [])

  const onNotification = useCallback((listener: MessageListener) => {
    notificationListeners.current.add(listener)
    return () => notificationListeners.current.delete(listener)
  }, [])

  const value = useMemo<WebSocketValue>(
    () => ({ status, subscribe, unsubscribe, send, onMessage, onNotification }),
    [status, subscribe, unsubscribe, send, onMessage, onNotification],
  )

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>
}

/** Listener registration that is safe to call unconditionally in render.
 *
 * Effects cannot be conditional, so components call this in a `useEffect` and
 * the listener identity is not part of the deps — the ref is stable.
 */
export function useSocketListener(
  event: 'message' | 'notification',
  listener: MessageListener,
): void {
  const { onMessage, onNotification } = useSocket()
  const ref = useRef(listener)
  ref.current = listener
  const register = event === 'message' ? onMessage : onNotification
  useEffect(() => register((frame) => ref.current(frame)), [register, event])
}

/** Subscribe to a thread for as long as this component is mounted. */
export function useThreadSubscription(threadId: string | undefined): void {
  const { status, subscribe, unsubscribe } = useSocket()
  useEffect(() => {
    if (!threadId || status !== 'open') return
    subscribe(threadId)
    return () => unsubscribe(threadId)
  }, [threadId, status, subscribe, unsubscribe])
}