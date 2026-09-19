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
