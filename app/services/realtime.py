"""Event broadcaster ringan untuk update dashboard secara real-time (SSE)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any


class RealtimeBroker:
    """Pub/sub in-memory untuk mengirim notifikasi perubahan data ke klien SSE."""

    def __init__(self) -> None:
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]] = set()

    def subscribe(self) -> asyncio.Queue[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
        self._subscribers.add((loop, queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        to_remove = [item for item in self._subscribers if item[1] is queue]
        for item in to_remove:
            self._subscribers.discard(item)

    def publish(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        payload = json.dumps(
            {
                "event": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": data or {},
            },
            default=str,
        )
        dead: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]] = []
        for loop, queue in list(self._subscribers):
            if loop.is_closed():
                dead.append((loop, queue))
                continue
            try:
                loop.call_soon_threadsafe(_put_nowait_safe, queue, payload)
            except RuntimeError:
                dead.append((loop, queue))
        for item in dead:
            self._subscribers.discard(item)


def _put_nowait_safe(queue: asyncio.Queue[str], payload: str) -> None:
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(payload)


realtime_broker = RealtimeBroker()
