import asyncio
import logging
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._user_sockets: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._subscriptions: dict[WebSocket, set[UUID]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._user_sockets[user_id].add(websocket)

    async def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._user_sockets[user_id].discard(websocket)
            self._subscriptions.pop(websocket, None)
            if not self._user_sockets[user_id]:
                self._user_sockets.pop(user_id, None)

    async def subscribe(self, websocket: WebSocket, thread_id: UUID) -> None:
        self._subscriptions[websocket].add(thread_id)

    async def unsubscribe(self, websocket: WebSocket, thread_id: UUID) -> None:
        self._subscriptions[websocket].discard(thread_id)

    async def broadcast_thread(
        self, thread_id: UUID, frame: dict, exclude: WebSocket | None = None
    ) -> None:
        async with self._lock:
            recipients = [
                websocket
                for websocket, subscriptions in self._subscriptions.items()
                if thread_id in subscriptions and websocket is not exclude
            ]
        await self._send_many(recipients, frame)

    async def send_user(self, user_id: UUID, frame: dict) -> None:
        async with self._lock:
            recipients = list(self._user_sockets.get(user_id, ()))
        await self._send_many(recipients, frame)

    async def send_user_except_thread(
        self, user_id: UUID, thread_id: UUID, frame: dict
    ) -> None:
        async with self._lock:
            recipients = [
                websocket
                for websocket in self._user_sockets.get(user_id, ())
                if thread_id not in self._subscriptions.get(websocket, set())
            ]
        await self._send_many(recipients, frame)

    async def _send_many(self, sockets: list[WebSocket], frame: dict) -> None:
        failed: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(frame)
            except Exception:
                logger.debug("Removing disconnected WebSocket after send failure", exc_info=True)
                failed.append(websocket)
        if failed:
            async with self._lock:
                for websocket in failed:
                    self._subscriptions.pop(websocket, None)
                    for user_id, user_sockets in self._user_sockets.items():
                        user_sockets.discard(websocket)
                for user_id in [key for key, value in self._user_sockets.items() if not value]:
                    self._user_sockets.pop(user_id, None)


manager = ConnectionManager()
