"""
Task graph model for the orchestration engine.
Represents ordered/parallel tasks with explicit dependencies.
"""
from __future__ import annotations
import uuid
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Task(BaseModel):
    """A single unit of work in the pipeline."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = Field(description="Human-readable task name, e.g. 'extract_jd'")
    agent: str = Field(description="Agent class responsible for this task, e.g. 'JDAnalyser'")
    depends_on: list[str] = Field(default_factory=list, description="List of task names this depends on")
    status: TaskStatus = TaskStatus.PENDING
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3


class TaskGraph(BaseModel):
    """
    Directed acyclic graph of tasks representing the full pipeline execution plan.
    Tasks may run in parallel if they share no dependencies.
    """
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tasks: list[Task] = Field(default_factory=list)

    def get_task_by_name(self, name: str) -> Task | None:
        for task in self.tasks:
            if task.name == name:
                return task
        return None

    def get_ready_tasks(self) -> list[Task]:
        """Return tasks whose dependencies are all completed and that are still pending."""
        completed_names = {t.name for t in self.tasks if t.status == TaskStatus.COMPLETED}
        ready = []
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            if all(dep in completed_names for dep in task.depends_on):
                ready.append(task)
        return ready

    def is_complete(self) -> bool:
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for t in self.tasks)

    def has_failed(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self.tasks)

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "total_tasks": len(self.tasks),
            "completed": sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in self.tasks if t.status == TaskStatus.FAILED),
            "pending": sum(1 for t in self.tasks if t.status == TaskStatus.PENDING),
            "running": sum(1 for t in self.tasks if t.status == TaskStatus.RUNNING),
        }
