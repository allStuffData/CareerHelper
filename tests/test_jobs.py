"""Job manager pub/sub tests."""

from __future__ import annotations

import asyncio

from app.services.job_manager import JobManager


async def test_subscribe_replays_history_then_closes():
    jobs = JobManager()
    jobs.open_channel("gen-1")
    jobs.publish("gen-1", {"stage": "queued"})
    jobs.publish("gen-1", {"stage": "compiling_pdf"})
    jobs.publish("gen-1", {"stage": "completed"})

    stages = [event["stage"] async for event in jobs.subscribe("gen-1")]
    assert stages == ["queued", "compiling_pdf", "completed"]
    assert jobs.event_count("gen-1") == 3


async def test_subscribe_streams_live_events():
    jobs = JobManager()
    jobs.open_channel("gen-2")
    received: list[str] = []

    async def consume() -> None:
        async for event in jobs.subscribe("gen-2"):
            received.append(event["stage"])

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    jobs.publish("gen-2", {"stage": "calling_kimi"})
    jobs.publish("gen-2", {"stage": "completed"})
    await asyncio.wait_for(task, timeout=2)
    assert received == ["calling_kimi", "completed"]


async def test_publish_is_thread_safe_when_loop_bound():
    jobs = JobManager()
    jobs.bind_loop(asyncio.get_running_loop())
    jobs.open_channel("gen-3")
    received: list[str] = []

    async def consume() -> None:
        async for event in jobs.subscribe("gen-3"):
            received.append(event["stage"])

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)

    import threading

    def worker() -> None:
        jobs.publish("gen-3", {"stage": "calling_kimi"})
        jobs.publish("gen-3", {"stage": "failed"})

    thread = threading.Thread(target=worker)
    thread.start()
    await asyncio.wait_for(task, timeout=2)
    thread.join()
    assert received == ["calling_kimi", "failed"]


async def test_submit_tracks_and_waits_for_task():
    jobs = JobManager()
    jobs.open_channel("gen-4")
    seen = []

    async def coro() -> None:
        seen.append("ran")

    jobs.submit("gen-4", coro)
    assert jobs.is_active("gen-4")
    await jobs.wait("gen-4")
    assert seen == ["ran"]
    assert jobs.active_count() == 0


async def test_shutdown_cancels_pending_tasks():
    jobs = JobManager()
    jobs.open_channel("gen-5")

    async def coro() -> None:
        await asyncio.sleep(60)

    jobs.submit("gen-5", coro)
    await asyncio.sleep(0.01)
    assert jobs.is_active("gen-5")
    await jobs.shutdown()
    assert jobs.active_count() == 0


async def test_subscribe_stops_when_the_producer_is_gone():
    """A dead producer must not leave the SSE subscriber blocked forever.

    Orphaned rows (their process was killed mid-run) have no task to publish a
    terminal event, so `subscribe` used to sit on ``queue.get()`` indefinitely.
    """
    jobs = JobManager()
    jobs.open_channel("gen-orphan")
    received: list[str] = []

    async def consume() -> None:
        async for event in jobs.subscribe(
            "gen-orphan", is_alive=lambda: False, poll_interval=0.01
        ):
            received.append(event["stage"])

    await asyncio.wait_for(consume(), timeout=2)
    assert received == []


async def test_subscribe_delivers_pending_events_before_giving_up():
    """An event published just before the producer died is still delivered."""
    jobs = JobManager()
    jobs.open_channel("gen-7")
    received: list[str] = []
    alive = True

    async def consume() -> None:
        async for event in jobs.subscribe(
            "gen-7", is_alive=lambda: alive, poll_interval=0.01
        ):
            received.append(event["stage"])

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.02)
    jobs.publish("gen-7", {"stage": "calling_kimi"})
    await asyncio.sleep(0.02)
    alive = False
    await asyncio.wait_for(task, timeout=2)
    assert received == ["calling_kimi"]


async def test_subscribe_without_is_alive_keeps_streaming():
    """Omitting ``is_alive`` preserves the original blocking behaviour."""
    jobs = JobManager()
    jobs.open_channel("gen-8")
    received: list[str] = []

    async def consume() -> None:
        async for event in jobs.subscribe("gen-8"):
            received.append(event["stage"])

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    assert received == []
    jobs.publish("gen-8", {"stage": "completed"})
    await asyncio.wait_for(task, timeout=2)
    assert received == ["completed"]
