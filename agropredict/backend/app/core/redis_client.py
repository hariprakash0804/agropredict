"""AgroPredict Backend - Redis Client"""

import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

# Global Redis connection pool
redis_client = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    health_check_interval=30,
    retry_on_timeout=True,
)


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency that returns the Redis client."""
    return redis_client


async def check_redis_connection() -> bool:
    """Check if Redis is reachable by sending a PING."""
    try:
        return await redis_client.ping()
    except Exception:
        return False
