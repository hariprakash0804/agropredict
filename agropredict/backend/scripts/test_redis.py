"""Test Redis connection."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.redis_client import redis_client

async def main():
    try:
        ping = await redis_client.ping()
        print("Redis Ping:", ping)
        await redis_client.set("test_key", "test_value")
        val = await redis_client.get("test_key")
        print("Redis Get:", val)
    except Exception as e:
        print("Redis error:", e)

if __name__ == "__main__":
    asyncio.run(main())
