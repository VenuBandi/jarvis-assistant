"""Authenticated routes own access checks; this generator owns bounded replay/disconnect."""
import asyncio
import json
import time


def frame(kind, data, event_id=None):
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return prefix + f"event: {kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def stream_events(request, bus, after=0, instance_id=None, heartbeat_s=10, poll_s=.25):
    cursor = after
    instance = instance_id
    last_heartbeat = 0
    while not await request.is_disconnected():
        batch = bus.read(cursor, instance)
        instance = batch["instance_id"]
        if batch["reset"]:
            snapshot = bus.snapshot()
            cursor = snapshot["cursor"]
            yield frame("reset", snapshot, cursor)
        else:
            for event in batch["events"]:
                if await request.is_disconnected():
                    return
                cursor = event["id"]
                yield frame("workflow", event, cursor)
        if time.monotonic() - last_heartbeat >= heartbeat_s:
            last_heartbeat = time.monotonic()
            yield frame("heartbeat", {"cursor": cursor, "instance_id": instance})
        if len(batch["events"]) >= 128 and not batch["reset"]:
            await asyncio.sleep(0)
        else:
            await asyncio.sleep(poll_s)
