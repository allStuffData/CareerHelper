"""In-process asyncio job manager with SSE-friendly pub/sub (Phase 2).

The local MVP runs one generation per process. This manager tracks running
tasks and fans progress events out to any number of SSE subscribers. Progress
events may be published from the event loop or from a worker thread (Phase 1
runs blocking LLM/LaTeX work), so :meth:`publish` bounces onto the bound loop
when necessary.

Before multi-instance hosting this is replaced by a durable Redis-backed
worker; the API layer only depends on this small interface.
"""

from __future__ import annotations

import asyncio
import threading
from typing import AsyncIterator, Callable, Coroutine, Optional

from app.contracts import STAGE_COMPLETED, STAGE_FAILED

TERMINAL_STAGES = {STAGE_COMPLETED, STAGE_FAILED}


class JobManager:
    """Track generation tasks and broadcast their progress events."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._history: dict[str, list[dict]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── loop binding ─────────────────────────────────────────────────────
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ── channels ─────────────────────────────────────────────────────────
    def open_channel(self, generation_id: str) -> None:
        with self._lock:
            self._history.setdefault(generation_id, [])
            self._subscribers.setdefault(generation_id, [])

    def has_events(self, generation_id: str) -> bool:
        with self._lock:
            return bool(self._history.get(generation_id))

    def history(self, generation_id: str) -> list[dict]:
        with self._lock:
            return list(self._history.get(generation_id, []))

    def event_count(self, generation_id: str) -> int:
        with self._lock:
            return len(self._history.get(generation_id, []))

    # ── publishing ───────────────────────────────────────────────────────
    def publish(self, generation_id: str, event: dict) -> None:
        """Publish an event to all current and future subscribers.

        Safe to call from any thread.
        """
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                current = asyncio.get_running_loop()
            except RuntimeError:
                current = None
            if current is loop:
                self._enqueue(generation_id, event)
            else:
                loop.call_soon_threadsafe(self._enqueue, generation_id, event)
        else:
            self._enqueue(generation_id, event)

    def _enqueue(self, generation_id: str, event: dict) -> None:
        terminal = event.get("stage") in TERMINAL_STAGES
        with self._lock:
            self._history.setdefault(generation_id, []).append(event)
            for queue in list(self._subscribers.get(generation_id, [])):
                queue.put_nowait(event)
                if terminal:
                    queue.put_nowait(None)

    # ── subscribing ──────────────────────────────────────────────────────
    async def subscribe(self, generation_id: str) -> AsyncIterator[dict]:
        """Yield progress events for ``generation_id``.

        Replays events already emitted, then streams live events until the
        terminal ``completed``/``failed`` event arrives.
        """
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            history = list(self._history.get(generation_id, []))
            terminal_already = any(
                event.get("stage") in TERMINAL_STAGES for event in history
            )
            self._subscribers.setdefault(generation_id, []).append(queue)
        try:
            for event in history:
                yield event
            if terminal_already:
                return
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            with self._lock:
                subscribers = self._subscribers.get(generation_id)
                if subscribers and queue in subscribers:
                    subscribers.remove(queue)

    # ── tasks ────────────────────────────────────────────────────────────
    def submit(
        self, generation_id: str, coro_factory: Callable[[], Coroutine]
    ) -> asyncio.Task:
        task = asyncio.create_task(
            coro_factory(), name=f"generation:{generation_id}"
        )
        self._tasks[generation_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(generation_id, None))
        return task

    def is_active(self, generation_id: str) -> bool:
        task = self._tasks.get(generation_id)
        return task is not None and not task.done()

    def active_count(self) -> int:
        return len(self._tasks)

    async def wait(self, generation_id: str) -> None:
        task = self._tasks.get(generation_id)
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                raise

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
