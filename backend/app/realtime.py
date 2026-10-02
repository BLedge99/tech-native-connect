"""WebSocket connection registry. decisions/0005-websocket-in-process.md.

ponytail: in-process registry, single uvicorn worker. Correct for one backend
container. Upgrade path: Redis pub/sub + a subscriber per worker, which changes
this class's internals only — send/broadcast API stays the same.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._user_sockets: dict[Any, set[WebSocket]] = defaultdict(set)
        self._thread_sockets: dict[Any, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect_user(self, user_id: Any, ws: WebSocket) -> None:
        async with self._lock:
            self._user_sockets[user_id].add(ws)

    async def disconnect(self, user_id: Any, ws: WebSocket) -> None:
        async with self._lock:
            self._user_sockets[user_id].discard(ws)
            if not self._user_sockets[user_id]:
                self._user_sockets.pop(user_id, None)
            for sockets in self._thread_sockets.values():
                sockets.discard(ws)

    async def subscribe_thread(self, user_id: Any, thread_id: Any, ws: WebSocket) -> None:
        async with self._lock:
            self._thread_sockets[thread_id].add(ws)
            self._user_sockets[user_id].add(ws)

    async def unsubscribe_thread(self, thread_id: Any, ws: WebSocket) -> None:
        async with self._lock:
            sockets = self._thread_sockets.get(thread_id)
            if sockets:
                sockets.discard(ws)
                if not sockets:
                    self._thread_sockets.pop(thread_id, None)

    def thread_subscribers(self, thread_id: Any) -> set[WebSocket]:
        return set(self._thread_sockets.get(thread_id, ()))

    def user_sockets(self, user_id: Any) -> set[WebSocket]:
        return set(self._user_sockets.get(user_id, ()))

    async def send_to(self, ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            # A dead socket must never raise into the caller — that is how one
            # dropped connection takes down a message broadcast.
            pass

    async def broadcast_to_thread(
        self,
        thread_id: Any,
        payload: dict,
        *,
        exclude: WebSocket | None = None,
        exclude_user_id: Any = None,
    ) -> None:
        """exclude drops one socket (the socket that sent it).
        exclude_user_id drops every socket belonging to the author — needed on
        the HTTP send path, where we know who sent it but not which socket did.
        Either without it and the sender sees their own message twice."""
        targets = self.thread_subscribers(thread_id)
        if exclude is not None:
            targets.discard(exclude)
        if exclude_user_id is not None:
            own = self.user_sockets(exclude_user_id)
            targets -= own
        await asyncio.gather(*(self.send_to(ws, payload) for ws in targets))

    async def broadcast_to_user(self, user_id: Any, payload: dict) -> None:
        targets = self.user_sockets(user_id)
        await asyncio.gather(*(self.send_to(ws, payload) for ws in targets))


manager = ConnectionManager()