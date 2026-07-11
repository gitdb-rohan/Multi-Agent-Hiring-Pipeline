import logging
import asyncio
from typing import Any, Callable, TypeVar, Awaitable
from functools import wraps
from pydantic import BaseModel
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

T = TypeVar("T")

def with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator to retry an async function with exponential backoff."""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = base_delay
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Failed after {max_retries} attempts: {e}")
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    delay *= 2
        return wrapper
    return decorator


class BaseAgent:
    """Base class for all agents."""
    
    def __init__(self, name: str):
        self.name = name

    async def run(self, *args, **kwargs) -> BaseModel:
        """
        The main entrypoint for the agent.
        Should be implemented by subclasses.
        Returns a Pydantic BaseModel as the contract.
        """
        with tracer.start_as_current_span(f"{self.name}.run") as span:
            span.set_attribute("agent.name", self.name)
            try:
                result = await self._execute(*args, **kwargs)
                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def _execute(self, *args, **kwargs) -> BaseModel:
        raise NotImplementedError("Subclasses must implement _execute")
