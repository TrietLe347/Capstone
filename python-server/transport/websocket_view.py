# transport/websocket_view.py
import asyncio
import threading
from typing import Set, Optional
from websockets.asyncio.server import serve, ServerConnection

from notifier.observer import IObserver
from payload.adapter import IPayloadAdapter
import numpy as np

class WebSocketView(IObserver):
    """
    Observer View that publishes the latest pose to all WebSocket clients.
    - Thread-safe: model updates may come from a camera thread.
    - Uses Adapter to convert ndarray -> JSON text.
    """
    def __init__(self, adapter: IPayloadAdapter, host: str = "127.0.0.1", port: int = 8765, hz: float = 30.0) -> None:
        self.adapter = adapter
        self.host = host
        self.port = port
        self.hz = hz

        self._latest_text: Optional[str] = None
        self._lock = threading.Lock()
        self._clients: Set[ServerConnection] = set()

    # ---- Observer API ----
    def update(self, arr33x4: np.ndarray) -> None:
        text = self.adapter.to_text(arr33x4)
        with self._lock:
            self._latest_text = text

    # ---- WebSocket server ----
    async def _handler(self, ws: ServerConnection) -> None:
        self._clients.add(ws)
        try:
            # Drain any inbound messages (optional: map to Commands later)
            async for _ in ws:
                pass
        finally:
            self._clients.discard(ws)

    async def _broadcast_loop(self) -> None:
        period = 1.0 / self.hz
        while True:
            # snapshot latest payload safely
            with self._lock:
                text = self._latest_text
            if text and self._clients:
                await asyncio.gather(
                    *(c.send(text) for c in list(self._clients)),
                    return_exceptions=True
                )
            await asyncio.sleep(period)

    async def run(self) -> None:
        print(f"[WS] Listening on ws://{self.host}:{self.port}")
        async with serve(self._handler, self.host, self.port, max_size=10_000_000):
            await self._broadcast_loop()
