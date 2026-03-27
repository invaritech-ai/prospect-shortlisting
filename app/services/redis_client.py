"""Shared Redis client singleton for caching across services."""
from __future__ import annotations

from app.core.config import settings

_client = None
_checked = False


def get_redis():
    """Return a Redis client, or None if Redis is unavailable.

    Lazy-initialized singleton — connects once, reuses forever.
    """
    global _client, _checked  # noqa: PLW0603
    if _checked:
        return _client
    _checked = True
    try:
        import redis  # type: ignore[import]
        r = redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        r.ping()
        _client = r
    except Exception:  # noqa: BLE001
        _client = None
    return _client
