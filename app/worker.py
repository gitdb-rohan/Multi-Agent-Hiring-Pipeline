import asyncio
from celery import Celery
from app.config import settings
from app.infra.db import get_db_session, Run, PipelineContext, TaskState
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)

celery_app = Celery(
    "hiring_pipeline",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Need to run async code inside celery sync task
def run_async(coro):
    return asyncio.run(coro)

async def async_run_pipeline_task(run_id: str):
    from app.orchestration.state_machine import PipelineStateMachine
    from app.agents.planner import PlannerAgent, PlannerRequest
    
    async for db in get_db_session():
        db_run = await db.get(Run, run_id)
        if not db_run:
            logger.error(f"Run {run_id} not found")
            return
            
        if db_run.status in ["completed", "failed"]:
            return

        # Fetch context
        context_result = await db.execute(select(PipelineContext).where(PipelineContext.run_id == run_id))
        context_obj = context_result.scalars().first()
        context = context_obj.context_data if context_obj else {}

        # Re-plan to build graph
        planner = PlannerAgent()
        planner.context = context
        request = PlannerRequest(
            run_id=run_id,
            goal_text=db_run.goal_text,
            raw_jd_text=context.get("raw_jd_text", ""),
            top_k=context.get("top_k", 5)
        )
        planner_response = await planner.run(request)
        task_graph = planner_response.task_graph
        
        # Hydrate task status from db
        task_states = await db.execute(select(TaskState).where(TaskState.run_id == run_id))
        completed_agents = {t.agent_name for t in task_states.scalars() if t.status == "COMPLETED"}
        
        for task in task_graph.tasks:
            if task.agent in completed_agents:
                task.status = "COMPLETED"

        machine = PipelineStateMachine(task_graph, context)
        # Restore state
        if db_run.status == "paused_for_review":
            machine.state = "paused_for_review"

        result = await machine.run(db=db)

        # Save context
        if not context_obj:
            context_obj = PipelineContext(run_id=run_id, context_data=machine.context)
            db.add(context_obj)
        else:
            context_obj.context_data = machine.context
            db.add(context_obj)

        db_run.status = result.get("status", "failed")
        await db.commit()

@celery_app.task(name="run_pipeline_task")
def run_pipeline_task(run_id: str):
    run_async(async_run_pipeline_task(run_id))
