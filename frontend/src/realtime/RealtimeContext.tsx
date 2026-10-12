import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';

export type RealtimeEvent = {
  type: string;
  data: Record<string, unknown>;
  thread_id?: string;
};

type RealtimeState = {
  connected: boolean;
  events: RealtimeEvent[];
  subscribedThreads: string[];
  subscribe: (threadId: string) => () => void;
};

const RealtimeContext = createContext<RealtimeState | null>(null);

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const socket = useRef<WebSocket | null>(null);
  const subscriptions = useRef(new Set<string>());
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<RealtimeEvent[]>([]);
  const [subscribedThreads, setSubscribedThreads] = useState<string[]>([]);

  useEffect(() => {
    if (!user) {
      socket.current?.close();
      socket.current = null;
      setConnected(false);
      setEvents([]);
      setSubscribedThreads([]);
      subscriptions.current.clear();
      return;
    }

    let stopped = false;
    let retryTimer: number | undefined;
    let delay = 1000;

    function connect() {
      if (stopped) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const current = new WebSocket(`${protocol}//${window.location.host}/api/v1/ws`);
      socket.current = current;
      current.onopen = () => {
        delay = 1000;
        setConnected(true);
        for (const threadId of subscriptions.current) {
          current.send(JSON.stringify({ type: 'subscribe', thread_id: threadId }));
        }
      };
      current.onmessage = (event) => {
        try {
          const frame = JSON.parse(String(event.data)) as RealtimeEvent;
          const threadId = frame.thread_id;
          if (frame.type === 'subscribed' && threadId && subscriptions.current.has(threadId)) {
            setSubscribedThreads((previous) => previous.includes(threadId)
              ? previous
              : [...previous, threadId]);
          }
          setEvents((previous) => [...previous.slice(-99), frame]);
        } catch {
          console.warn('Ignored malformed realtime event.');
        }
      };
      current.onclose = () => {
        if (socket.current === current) socket.current = null;
        setConnected(false);
        setSubscribedThreads([]);
        if (stopped) return;
        const jitter = Math.random() * Math.min(delay * 0.25, 1000);
        retryTimer = window.setTimeout(connect, delay + jitter);
        delay = Math.min(delay * 2, 30000);
      };
      current.onerror = () => current.close();
    }

    connect();
    return () => {
      stopped = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      socket.current?.close();
      socket.current = null;
      setConnected(false);
      setSubscribedThreads([]);
    };
  }, [user?.id]);

  const subscribe = useCallback((threadId: string) => {
    subscriptions.current.add(threadId);
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify({ type: 'subscribe', thread_id: threadId }));
    }
    return () => {
      subscriptions.current.delete(threadId);
      setSubscribedThreads((previous) => previous.filter((id) => id !== threadId));
      if (socket.current?.readyState === WebSocket.OPEN) {
        socket.current.send(JSON.stringify({ type: 'unsubscribe', thread_id: threadId }));
      }
    };
  }, []);

  return (
    <RealtimeContext.Provider value={{ connected, events, subscribedThreads, subscribe }}>
      {children}
    </RealtimeContext.Provider>
  );
}

export function useRealtime() {
  const realtime = useContext(RealtimeContext);
  if (!realtime) throw new Error('useRealtime must be used inside RealtimeProvider');
  return realtime;
}
