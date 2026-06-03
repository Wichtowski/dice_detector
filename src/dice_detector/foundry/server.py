import asyncio
import json
import threading

import websockets
from websockets.server import WebSocketServerProtocol

from dice_detector.models import RollResult


class FoundryWebSocketServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8767) -> None:
        self.host = host
        self.port = port
        self._clients: set[WebSocketServerProtocol] = set()
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> bool:
        if self._running:
            return True
        try:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            self._running = True
            return True
        except Exception:
            self._running = False
            return False

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        async with websockets.serve(self._handler, self.host, self.port):
            await asyncio.Future()

    async def _handler(self, websocket: WebSocketServerProtocol) -> None:
        self._clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def stop(self) -> None:
        self._running = False
        self._clients.clear()

    def send_roll(self, result: RollResult) -> bool:
        if not self._clients or not self._loop:
            return False
        payload = json.dumps(
            {
                "type": "roll",
                "message": result.to_markdown(),
                "result": result.model_dump(mode="json"),
            }
        )
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)
        return True

    async def _broadcast(self, payload: str) -> None:
        dead: list[WebSocketServerProtocol] = []
        for client in self._clients:
            try:
                await client.send(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            self._clients.discard(client)
