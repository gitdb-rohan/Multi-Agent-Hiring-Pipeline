import logging
import time
import redis.asyncio as redis
from app.config import settings

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """
    Redis-backed token bucket rate limiter.
    Ensures we don't exceed a specified rate for external API calls (e.g. email sends).
    """

    def __init__(self, key: str, max_tokens: int, refill_rate_per_minute: int):
        """
        Args:
            key: Redis key for this bucket.
            max_tokens: Maximum burst capacity.
            refill_rate_per_minute: How many tokens are added per minute.
        """
        self.key = f"rate_limit:{key}"
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate_per_minute
        self.redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self.redis is None:
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self.redis

    async def acquire(self) -> bool:
        """
        Try to acquire a token. Returns True if allowed, False if rate limited.
        Uses a Lua script for atomic check-and-decrement.
        """
        r = await self._get_redis()

        lua_script = """
        local key = KEYS[1]
        local max_tokens = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        local data = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(data[1])
        local last_refill = tonumber(data[2])

        if tokens == nil then
            tokens = max_tokens
            last_refill = now
        end

        -- Refill tokens based on elapsed time
        local elapsed = now - last_refill
        local refill = elapsed * refill_rate / 60.0
        tokens = math.min(max_tokens, tokens + refill)
        last_refill = now

        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
            redis.call('EXPIRE', key, 120)
            return 1
        else
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
            redis.call('EXPIRE', key, 120)
            return 0
        end
        """
        
        try:
            result = await r.eval(lua_script, 1, self.key, self.max_tokens, self.refill_rate, time.time())
            return bool(result)
        except Exception as e:
            logger.warning(f"Rate limiter error (allowing request): {e}")
            return True  # Fail open

    async def check_remaining(self) -> float:
        """Check how many tokens remain without consuming one."""
        r = await self._get_redis()
        try:
            data = await r.hmget(self.key, "tokens", "last_refill")
            tokens = float(data[0]) if data[0] else float(self.max_tokens)
            return tokens
        except Exception:
            return float(self.max_tokens)

    async def close(self):
        if self.redis:
            await self.redis.aclose()


class RedisTaskQueue:
    """
    Simple Redis-backed task queue for decoupling request acceptance from processing.
    """

    def __init__(self, queue_name: str = "pipeline_tasks"):
        self.queue_name = queue_name
        self.redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self.redis is None:
            self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self.redis

    async def enqueue(self, task_data: str) -> int:
        """Push a task onto the queue. Returns queue length."""
        r = await self._get_redis()
        return await r.rpush(self.queue_name, task_data)

    async def dequeue(self, timeout: int = 0) -> str | None:
        """Pop a task from the queue. Blocks for timeout seconds if queue is empty."""
        r = await self._get_redis()
        result = await r.blpop(self.queue_name, timeout=timeout)
        if result:
            return result[1]
        return None

    async def length(self) -> int:
        r = await self._get_redis()
        return await r.llen(self.queue_name)

    async def close(self):
        if self.redis:
            await self.redis.aclose()


# Pre-configured rate limiter for email sending
email_rate_limiter = TokenBucketRateLimiter(
    key="email_send",
    max_tokens=settings.EMAIL_SEND_RATE_PER_MINUTE,
    refill_rate_per_minute=settings.EMAIL_SEND_RATE_PER_MINUTE,
)

# Shared task queue
task_queue = RedisTaskQueue()
