import json
import logging
from typing import Any, Optional

import redis

from app.config import settings

logger = logging.getLogger("eve.cache")

_client: Optional["redis.Redis"] = None
_client_broken = False  # set once a connection attempt fails, so we stop retrying every request


def _get_client() -> Optional["redis.Redis"]:
    """
    Lazily creates a single shared Redis client. If Redis is unreachable (not
    configured, container not running, etc.) caching is silently disabled —
    the app must work correctly with or without Redis, it's a performance
    optimization, not a dependency.
    """
    global _client, _client_broken
    if _client_broken:
        return None
    if _client is None:
        try:
            _client = redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
            _client.ping()
        except Exception as exc:  # noqa: BLE001 - any failure here just disables caching
            logger.warning("cache_unavailable reason=%s", exc)
            _client_broken = True
            _client = None
    return _client


def cache_get(key: str) -> Optional[Any]:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_get_failed key=%s reason=%s", key, exc)
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 30) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_set_failed key=%s reason=%s", key, exc)


def cache_delete(*keys: str) -> None:
    client = _get_client()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_delete_failed keys=%s reason=%s", keys, exc)
