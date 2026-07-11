"""
Custom orchestration state machine.
Drives the pipeline through: PENDING → PLANNING → DISPATCHING → RUNNING → EVALUATING → (DONE | NEEDS_REVIEW | FAILED)
"""
from __future__ import annotations
import time
import logging
import asyncio
from enum import Enum
from typing import Any

from app.orchestration.task_graph import TaskGraph, Task, TaskStatus
from app.orchestration.events import event_emitter

from app.agents.jd_analyser import JDAnalyser, JDAnalyserRequest
from app.agents.candidate_scorer import CandidateScorer, CandidateScorerRequest
from app.agents.outreach_drafter import OutreachDrafter, OutreachDrafterRequest
from app.schemas.jd import ExtractedJD
from app.schemas.candidate import ScoredCandidate

logger = logging.getLogger(__name__)


class PipelineState(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    EVALUATING = "evaluating"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


# Registry mapping agent names to their classes
AGENT_REGISTRY = {
    "JDAnalyser": JDAnalyser,
    "CandidateScorer": CandidateScorer,
    "OutreachDrafter": OutreachDrafter,
}


class PipelineStateMachine:
    """
    Drives a TaskGraph through the pipeline lifecycle.
    Each state transition is emitted as an SSE event for real-time frontend updates.
    """

    def __init__(self, task_graph: TaskGraph):
        self.task_graph = task_graph
        self.state = PipelineState.PENDING
        self.run_id = task_graph.run_id
        # Shared context between tasks so outputs flow to downstream inputs
        self.context: dict[str, Any] = {}
        self.eval_results: list[dict] = []

    async def _transition(self, new_state: PipelineState):
        old = self.state
        self.state = new_state
        logger.info(f"[{self.run_id}] State: {old.value} → {new_state.value}")
        await event_emitter.emit_state_change(self.run_id, old.value, new_state.value)

    async def run(self) -> dict[str, Any]:
        """Execute the full pipeline."""
        try:
            await self._transition(PipelineState.PLANNING)
            # Planning is already done (TaskGraph was built by Planner), move to dispatch
            await self._transition(PipelineState.DISPATCHING)
            await self._transition(PipelineState.RUNNING)

            max_iterations = len(self.task_graph.tasks) * 3  # safety
            iteration = 0

            while not self.task_graph.is_complete() and not self.task_graph.has_failed():
                iteration += 1
                if iteration > max_iterations:
                    logger.error(f"[{self.run_id}] Max iterations exceeded")
                    await self._transition(PipelineState.FAILED)
                    return {"status": "failed", "error": "Max iterations exceeded"}

                ready_tasks = self.task_graph.get_ready_tasks()
                if not ready_tasks:
                    if self.task_graph.has_failed():
                        break
                    # No ready tasks but not complete — something is wrong
                    logger.error(f"[{self.run_id}] Deadlock: no ready tasks")
                    await self._transition(PipelineState.FAILED)
                    return {"status": "failed", "error": "Deadlock detected"}

                # Execute ready tasks (could be parallelized with asyncio.gather for independent tasks)
                for task in ready_tasks:
                    await self._execute_task(task)

            if self.task_graph.has_failed():
                await self._transition(PipelineState.FAILED)
                return {
                    "status": "failed",
                    "run_id": self.run_id,
                    "context": self.context,
                    "graph_summary": self.task_graph.summary(),
                }

            # Evaluating phase
            await self._transition(PipelineState.EVALUATING)
            needs_review = any(r.get("needs_human_review") for r in self.eval_results)

            if needs_review:
                await self._transition(PipelineState.NEEDS_REVIEW)
            else:
                await self._transition(PipelineState.DONE)

            result = {
                "status": self.state.value,
                "run_id": self.run_id,
                "context": self.context,
                "eval_results": self.eval_results,
                "graph_summary": self.task_graph.summary(),
            }
            await event_emitter.emit_run_completed(self.run_id, self.state.value, self.task_graph.summary())
            return result

        except Exception as e:
            logger.exception(f"[{self.run_id}] Pipeline failed: {e}")
            await self._transition(PipelineState.FAILED)
            await event_emitter.emit_error(self.run_id, str(e))
            return {"status": "failed", "run_id": self.run_id, "error": str(e)}

    async def _execute_task(self, task: Task):
        """Execute a single task by dispatching to the appropriate agent."""
        agent_cls = AGENT_REGISTRY.get(task.agent)
        if not agent_cls:
            task.status = TaskStatus.FAILED
            task.error = f"Unknown agent: {task.agent}"
            return

        task.status = TaskStatus.RUNNING
        await event_emitter.emit_agent_started(self.run_id, task.agent, task.name)
        start = time.time()

        try:
            agent = agent_cls()
            request = self._build_request(task)
            result = await agent.run(request)

            elapsed = time.time() - start
            task.status = TaskStatus.COMPLETED

            # Store output in context for downstream tasks
            self._store_result(task, result)

            summary = self._summarize_result(task, result)
            await event_emitter.emit_agent_completed(self.run_id, task.agent, task.name, elapsed, summary)

        except Exception as e:
            elapsed = time.time() - start
            task.retry_count += 1
            if task.retry_count >= task.max_retries:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                logger.error(f"[{self.run_id}] Task {task.name} failed after {task.retry_count} retries: {e}")
            else:
                task.status = TaskStatus.PENDING  # re-queue for retry
                logger.warning(f"[{self.run_id}] Task {task.name} failed (attempt {task.retry_count}): {e}")

    def _build_request(self, task: Task) -> Any:
        """Build the agent-specific request from the shared context."""
        if task.agent == "JDAnalyser":
            return JDAnalyserRequest(raw_text=self.context.get("raw_jd_text", ""))

        elif task.agent == "CandidateScorer":
            jd_data = self.context.get("extracted_jd")
            if isinstance(jd_data, dict):
                jd = ExtractedJD(**jd_data)
            else:
                jd = jd_data
            return CandidateScorerRequest(
                jd=jd,
                top_k=self.context.get("top_k", 5),
            )

        elif task.agent == "OutreachDrafter":
            jd_data = self.context.get("extracted_jd")
            if isinstance(jd_data, dict):
                jd = ExtractedJD(**jd_data)
            else:
                jd = jd_data
            
            candidates_data = self.context.get("scored_candidates", [])
            candidates = []
            for c in candidates_data:
                if isinstance(c, dict):
                    candidates.append(ScoredCandidate(**c))
                else:
                    candidates.append(c)
            
            return OutreachDrafterRequest(jd=jd, scored_candidates=candidates)

        raise ValueError(f"Cannot build request for agent: {task.agent}")

    def _store_result(self, task: Task, result: Any):
        """Store agent output into shared context."""
        if task.agent == "JDAnalyser":
            self.context["extracted_jd"] = result.model_dump()
        elif task.agent == "CandidateScorer":
            self.context["scored_candidates"] = [c.model_dump() for c in result.scored_candidates]
        elif task.agent == "OutreachDrafter":
            self.context["outreach_emails"] = [e.model_dump() for e in result.emails]
            self.context["send_results"] = result.send_results

    def _summarize_result(self, task: Task, result: Any) -> str:
        """Generate a human-readable summary for SSE."""
        if task.agent == "JDAnalyser":
            return f"Extracted {len(result.required_skills)} required skills, confidence {result.confidence}"
        elif task.agent == "CandidateScorer":
            return f"Scored {len(result.scored_candidates)} candidates"
        elif task.agent == "OutreachDrafter":
            return f"Drafted {len(result.emails)} outreach emails"
        return "Completed"
