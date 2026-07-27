import logging
import asyncio
import random
import hashlib
from typing import Any, Callable, TypeVar, Awaitable
from functools import wraps
from pydantic import BaseModel
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.infra.db import TaskState

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

T = TypeVar("T")

def with_retry(max_retries: int = 3, base_delay: float = 1.0, jitter_factor: float = 0.2):
    """Decorator to retry an async function with exponential backoff and jitter."""
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
                    
                    jitter = delay * jitter_factor * random.uniform(-1, 1)
                    sleep_time = max(0, delay + jitter)
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {sleep_time:.2f}s...")
                    await asyncio.sleep(sleep_time)
                    delay *= 2
        return wrapper
    return decorator


class BaseAgent:
    """Base class for all agents."""
    
    TASK_DESCRIPTION: str = "Base task description"

    def __init__(self, name: str):
        self.name = name

    def build_request(self, context: dict[str, Any]) -> Any:
        raise NotImplementedError

    def store_result(self, result: Any, context: dict[str, Any]) -> None:
        raise NotImplementedError

    def get_summary(self, result: Any) -> str:
        raise NotImplementedError

    def get_eval_input_context(self, context: dict[str, Any]) -> str:
        raise NotImplementedError

    def _hash_request(self, request: BaseModel) -> str:
        req_json = request.model_dump_json(exclude_none=True)
        return hashlib.sha256(req_json.encode('utf-8')).hexdigest()

    async def run(self, request: BaseModel, run_id: str, db: AsyncSession | None = None) -> BaseModel:
        """
        The main entrypoint for the agent.
        Includes caching logic if db session is provided.
        """
        with tracer.start_as_current_span(f"{self.name}.run") as span:
            span.set_attribute("agent.name", self.name)
            
            input_hash = self._hash_request(request)
            
            # Check Cache
            if db:
                result_state = await db.execute(
                    select(TaskState).where(
                        TaskState.run_id == run_id,
                        TaskState.agent_name == self.name,
                        TaskState.input_hash == input_hash,
                        TaskState.status == "COMPLETED"
                    )
                )
                cached = result_state.scalars().first()
                if cached and cached.output_json:
                    logger.info(f"[{self.name}] Cache hit for run_id={run_id}")
                    try:
                        return self.parse_cached_result(cached.output_json)
                    except NotImplementedError:
                        pass

            try:
                result = await self._execute(request)
                
                # Save to cache
                if db:
                    new_state = TaskState(
                        run_id=run_id,
                        agent_name=self.name,
                        status="COMPLETED",
                        input_hash=input_hash,
                        output_json=result.model_dump()
                    )
                    db.add(new_state)
                    await db.commit()
                
                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    def parse_cached_result(self, output_json: dict) -> BaseModel:
        """Subclasses should implement this to reconstruct the BaseModel from JSON cache."""
        raise NotImplementedError("Subclasses must implement parse_cached_result for caching support")

    async def _execute(self, request: BaseModel) -> BaseModel:
        raise NotImplementedError("Subclasses must implement _execute")
