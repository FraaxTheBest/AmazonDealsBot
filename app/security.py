import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message


class AdminOnlyMiddleware(BaseMiddleware):
    def __init__(self, admin_user_id: int) -> None:
        self.admin_user_id = int(admin_user_id)

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or int(user.id) == self.admin_user_id:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("Accesso non autorizzato.", show_alert=True)
        elif isinstance(event, Message):
            await event.answer("⛔ Accesso non autorizzato.")
        return None


class SimpleRateLimitMiddleware(BaseMiddleware):
    """Protezione leggera contro raffiche accidentali di update."""

    def __init__(self, max_updates: int = 60, window_seconds: int = 10) -> None:
        self.max_updates = max(10, int(max_updates))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        now = time.monotonic()
        bucket = self._events[int(user.id)]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_updates:
            if isinstance(event, CallbackQuery):
                await event.answer("Troppi comandi ravvicinati. Riprova tra poco.")
            return None
        bucket.append(now)
        return await handler(event, data)
