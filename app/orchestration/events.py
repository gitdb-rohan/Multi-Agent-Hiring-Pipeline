"""
SSE event schema and emitter for real-time streaming to the frontend.
"""
from __future__ import annotations
import json
import time
import asyncio
import logging
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    STATE_CHANGE = "state_change"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    EVAL_FLAGGED = "eval_flagged"
    RUN_COMPLETED = "run_completed"
    ERROR = "error"


class PipelineEvent(BaseModel):
    """A single SSE event emitted during pipeline execution."""
    event_type: EventType
    run_id: str
    timestamp: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as a Server-Sent Event string."""
        payload = self.model_dump_json()
        return f"event: {self.event_type.value}\ndata: {payload}\n\n"


class EventEmitter:
    """
    In-memory event emitter that supports multiple subscribers per run_id.
    Each subscriber gets an asyncio.Queue to consume events from.
    """

    def __init__(self):
        # run_id -> list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """Create a new subscriber queue for a run_id."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[run_id].append(queue)
        logger.info(f"New SSE subscriber for run {run_id}")
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue):
        """Remove a subscriber queue."""
        if run_id in self._subscribers:
            self._subscribers[run_id] = [q for q in self._subscribers[run_id] if q is not queue]
            if not self._subscribers[run_id]:
                del self._subscribers[run_id]

    async def emit(self, event: PipelineEvent):
        """Push an event to all subscribers of the given run_id."""
        run_id = event.run_id
        logger.debug(f"Emitting {event.event_type.value} for run {run_id}")
        for queue in self._subscribers.get(run_id, []):
            await queue.put(event)

    async def emit_state_change(self, run_id: str, old_state: str, new_state: str):
        await self.emit(PipelineEvent(
            event_type=EventType.STATE_CHANGE,
            run_id=run_id,
            data={"old_state": old_state, "new_state": new_state},
        ))

    async def emit_agent_started(self, run_id: str, agent_name: str, task_name: str):
        await self.emit(PipelineEvent(
            event_type=EventType.AGENT_STARTED,
            run_id=run_id,
            data={"agent": agent_name, "task": task_name},
        ))

    async def emit_agent_completed(self, run_id: str, agent_name: str, task_name: str, duration_s: float, summary: str = ""):
        await self.emit(PipelineEvent(
            event_type=EventType.AGENT_COMPLETED,
            run_id=run_id,
            data={"agent": agent_name, "task": task_name, "duration_s": round(duration_s, 2), "summary": summary},
        ))

    async def emit_eval_flagged(self, run_id: str, agent_name: str, reason: str):
        await self.emit(PipelineEvent(
            event_type=EventType.EVAL_FLAGGED,
            run_id=run_id,
            data={"agent": agent_name, "reason": reason},
        ))

    async def emit_run_completed(self, run_id: str, status: str, summary: dict):
        await self.emit(PipelineEvent(
            event_type=EventType.RUN_COMPLETED,
            run_id=run_id,
            data={"status": status, "summary": summary},
        ))

    async def emit_error(self, run_id: str, error: str):
        await self.emit(PipelineEvent(
            event_type=EventType.ERROR,
            run_id=run_id,
            data={"error": error},
        ))


# Global singleton event emitter
event_emitter = EventEmitter()
