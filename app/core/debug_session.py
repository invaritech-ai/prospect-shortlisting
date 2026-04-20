from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

_DEBUG_LOG_PATH = "/Users/avi/Documents/Projects/AI/Prospect_shortlisting/.cursor/debug-c83c0b.log"
_SESSION_ID = "c83c0b"


# region agent log
def append_agent_debug_log(
    *,
    location: str,
    message: str,
    hypothesis_id: str,
    data: dict[str, Any],
    run_id: str = "post-fix",
) -> None:
    payload = {
        "sessionId": _SESSION_ID,
        "id": f"log_{int(time.time() * 1000)}_{uuid4().hex[:8]}",
        "timestamp": int(time.time() * 1000),
        "location": location,
        "message": message,
        "data": data,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def safe_broker_target(redis_url: str) -> dict[str, Any]:
    parsed = urlparse(redis_url)
    db = parsed.path.lstrip("/") if parsed.path else ""
    return {
        "broker_scheme": parsed.scheme or "",
        "broker_host": parsed.hostname or "",
        "broker_port": parsed.port,
        "broker_db": db,
    }


# endregion
