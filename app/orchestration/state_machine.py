"""
Custom orchestration state machine.
Drives the pipeline through: PENDING → PLANNING → DISPATCHING → RUNNING → EVALUATING → (DONE | PAUSED_FOR_REVIEW | FAILED)
"""
from __future__ import annotations
import json
import time
import logging
import asyncio
from enum import Enum
from typing import Any

from app.orchestration.task_graph import TaskGraph, Task, TaskStatus
from app.orchestration.events import event_emitter

from app.agents.jd_analyser import JDAnalyser
from app.agents.candidate_scorer import CandidateScorer
from app.agents.outreach_drafter import OutreachDrafter
from app.evaluation.geval import evaluate_agent_output

logger = logging.getLogger(__name__)


class PipelineState(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    EVALUATING = "evaluating"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    PAUSED_FOR_REVIEW = "paused_for_review"
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

    def __init__(self, task_graph: TaskGraph, context: dict[str, Any] | None = None):
        self.task_graph = task_graph
        self.state = PipelineState.PENDING
        self.run_id = task_graph.run_id
        # Shared context between tasks so outputs flow to downstream inputs
        self.context: dict[str, Any] = context or {}
        self.eval_results: list[dict] = []
        # Flag to indicate if we need to pause the pipeline
        self.should_pause = False

    async def _transition(self, new_state: PipelineState):
        old = self.state
        self.state = new_state
        logger.info(f"[{self.run_id}] State: {old.value} → {new_state.value}")
        await event_emitter.emit_state_change(self.run_id, old.value, new_state.value)

    async def run(self, db=None) -> dict[str, Any]:
        """Execute the full pipeline."""
        try:
            if self.state in [PipelineState.PENDING, PipelineState.PAUSED_FOR_REVIEW, PipelineState.NEEDS_REVIEW]:
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

                # Execute ready tasks in parallel
                exec_tasks = [self._execute_task(task, db) for task in ready_tasks]
                await asyncio.gather(*exec_tasks)

                # After executing a tier, check if we need to pause for review
                if self.should_pause:
                    await self._transition(PipelineState.PAUSED_FOR_REVIEW)
                    return {
                        "status": self.state.value,
                        "run_id": self.run_id,
                        "context": self.context,
                        "eval_results": self.eval_results,
                        "graph_summary": self.task_graph.summary(),
                    }

            if self.task_graph.has_failed():
                await self._transition(PipelineState.FAILED)
                return {
                    "status": "failed",
                    "run_id": self.run_id,
                    "context": self.context,
                    "graph_summary": self.task_graph.summary(),
                }

            # Evaluating phase — check if any eval results flagged for review
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

    async def _execute_task(self, task: Task, db=None):
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
            request = agent.build_request(self.context)
            
            # Using db session if provided for caching
            result = await agent.run(request, run_id=self.run_id, db=db)

            elapsed = time.time() - start
            task.status = TaskStatus.COMPLETED

            # Store output in context for downstream tasks
            agent.store_result(result, self.context)

            # Run G-Eval on the agent's output
            eval_result = await self._evaluate_task(task, agent, result)
            if eval_result:
                self.eval_results.append(eval_result.model_dump())
                if eval_result.needs_human_review:
                    self.should_pause = True

            # If the agent is JDAnalyser, pause automatically for HITL
            if task.agent == "JDAnalyser":
                self.should_pause = True

            summary = agent.get_summary(result)
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

    async def _evaluate_task(self, task: Task, agent: Any, result: Any):
        """
        Run G-Eval (LLM-as-judge) on a completed task's output.
        """
        try:
            input_ctx = agent.get_eval_input_context(self.context)
            output_str = json.dumps(result.model_dump(), default=str) if hasattr(result, "model_dump") else str(result)

            eval_result = await evaluate_agent_output(
                agent_name=task.agent,
                task_id=task.id,
                task_description=agent.TASK_DESCRIPTION,
                input_context=input_ctx,
                agent_output=output_str,
            )

            if not eval_result:
                return None

            logger.info(
                f"[{self.run_id}] G-Eval for {task.agent}: "
                f"rel={eval_result.relevance:.2f} faith={eval_result.faithfulness:.2f} "
                f"comp={eval_result.completeness:.2f} "
                f"review={'YES' if eval_result.needs_human_review else 'no'}"
            )

            # Emit SSE event if flagged for review
            if eval_result.needs_human_review:
                await event_emitter.emit_eval_flagged(
                    self.run_id, task.agent, eval_result.review_reason or "Below threshold"
                )

            return eval_result

        except Exception as e:
            logger.error(f"[{self.run_id}] G-Eval failed for {task.agent}: {e}")
            return None
