from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_cache_json(redis: Redis, key: str) -> Any | None:
    try:
        raw = redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except (RedisError, json.JSONDecodeError):
        return None


def set_cache_json(redis: Redis, key: str, value: Any, ttl_seconds: int) -> bool:
    try:
        payload = json.dumps(value, default=str)
        redis.setex(key, ttl_seconds, payload)
        return True
    except (RedisError, TypeError, ValueError):
        return False


def clear_pattern(redis: Redis, pattern: str) -> int:
    try:
        keys = list(redis.scan_iter(match=pattern))
        if not keys:
            return 0
        return int(redis.delete(*keys))
    except RedisError:
        return 0


def clear_user_recs_cache(redis: Redis, user_id: str) -> int:
    return clear_pattern(redis, f"recs:{user_id}:*")
