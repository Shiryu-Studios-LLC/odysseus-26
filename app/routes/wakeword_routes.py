# routes/wakeword_routes.py
"""Wake word REST routes.

WebSocket is registered directly in app.py via @app.websocket() to avoid
BaseHTTPMiddleware / Starlette routing issues.
"""

import asyncio
import json
import logging
from typing import Set

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

_clients: Set[WebSocket] = set()
_router: APIRouter | None = None
_loop: asyncio.AbstractEventLoop | None = None
_wakeword_service = None


def setup_wakeword_routes(wakeword_service):
    """Build and return the wake word APIRouter."""
    global _router, _loop, _wakeword_service
    _wakeword_service = wakeword_service
    _router = APIRouter(prefix="/api/wakeword", tags=["wakeword"])

    # ── Detection callback (called from background thread) ────────────

    def _on_detection(wake_word: str, confidence: float):
        if _loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            _broadcast({"type": "detection", "wake_word": wake_word, "confidence": confidence}),
            _loop,
        )

    wakeword_service.register_callback(_on_detection)

    # ── REST endpoints ────────────────────────────────────────────────

    @_router.get("/status")
    async def status():
        return wakeword_service.get_status()

    @_router.post("/start")
    async def start():
        try:
            from src.settings import load_settings, save_settings
            s = load_settings()
            s["wakeword_enabled"] = True
            save_settings(s)
        except Exception:
            pass
        wakeword_service.update_config({"enabled": True})
        wakeword_service.start()
        return {"status": "started", **wakeword_service.get_status()}

    @_router.post("/stop")
    async def stop():
        try:
            from src.settings import load_settings, save_settings
            s = load_settings()
            s["wakeword_enabled"] = False
            save_settings(s)
        except Exception:
            pass
        wakeword_service.stop()
        return {"status": "stopped"}

    @_router.post("/config")
    async def config(request: Request):
        body = await request.json()
        wakeword_service.update_config(body)
        return wakeword_service.get_status()

    return _router


async def _broadcast(msg: dict):
    if not _clients:
        return
    text = json.dumps(msg)
    dead = set()
    for c in _clients:
        try:
            await c.send_text(text)
        except Exception:
            dead.add(c)
    _clients.difference_update(dead)
