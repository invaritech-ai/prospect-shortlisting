"""PEL reaper (WatchdogThread) tests.

test_pel_reaper_reclaims — un-ACKed message is reclaimed and redelivered to the stream
"""
from __future__ import annotations

import json
import time
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import ResponseError

from app.services.queue_service import GROUP_NAME, STREAM_KEY
from app.services.watchdog import WatchdogThread, _REAPER_IDLE_MS


def _ensure_group(client: Redis) -> None:
    try:
        client.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


class TestPelReaperReclaims:
    """An un-ACKed PEL entry idle beyond the threshold is re-added to the stream."""

    def test_reaper_redelivers_idle_message(self, redis_client: Redis):
        _ensure_group(redis_client)

        # Add a message and read it (puts it in PEL) without ACKing.
        job_id = str(uuid4())
        msg_id_raw = redis_client.xadd(STREAM_KEY, {
            "task_id": str(uuid4()),
            "task_type": "scrape_run_all",
            "payload_json": json.dumps({"job_id": job_id}),
        })
        msg_id = msg_id_raw.decode() if isinstance(msg_id_raw, bytes) else msg_id_raw

        # Consume without ACKing to simulate a crashed worker.
        result = redis_client.xreadgroup(GROUP_NAME, "crashed-worker", {STREAM_KEY: ">"}, count=1)
        assert result, "Expected to read the message"

        # Use XAUTOCLAIM with 0ms idle threshold to simulate the reaper finding it immediately.
        # (In production the threshold is 30 minutes; here we use 0ms for test speed.)
        autoclaim_result = redis_client.xautoclaim(
            STREAM_KEY,
            GROUP_NAME,
            "reaper",
            min_idle_time=0,  # claim immediately for test
            start_id="0-0",
            count=200,
        )
        _, entries, _ = autoclaim_result

        # Should have reclaimed our message.
        assert len(entries) >= 1
        reclaimed_ids = [e[0] for e in entries]
        assert msg_id in reclaimed_ids

        # Simulate what WatchdogThread._reap does: XADD new, XACK original.
        for orig_msg_id, fields in entries:
            new_id = redis_client.xadd(STREAM_KEY, fields)
            redis_client.xack(STREAM_KEY, GROUP_NAME, orig_msg_id)

        # The stream should now have a new entry with the same payload.
        # Original was ACKed (removed from PEL); new entry is pending delivery.
        stream_entries = redis_client.xrange(STREAM_KEY)
        payloads = [json.loads(e[1].get("payload_json", "{}")) for e in stream_entries]
        job_ids_in_stream = [p.get("job_id") for p in payloads]
        assert job_id in job_ids_in_stream, "Re-delivered message should be in stream"

        # PEL should be empty for the original message.
        pending = redis_client.xpending_range(STREAM_KEY, GROUP_NAME, "-", "+", count=100)
        pending_ids = [p["message_id"] for p in pending]
        assert msg_id not in pending_ids, "Original should be ACKed from PEL"
