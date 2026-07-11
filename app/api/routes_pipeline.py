import asyncio
import json
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.agents.planner import PlannerAgent, PlannerRequest
from app.orchestration.events import event_emitter
from app.infra.redis_client import task_queue
from app.infra.db import Run
from app.dependencies import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class RunPipelineRequest(BaseModel):
    goal_text: str
    raw_jd_text: str
    top_k: int = 5


class RunPipelineResponse(BaseModel):
    run_id: str
    status: str
    message: str


async def execute_pipeline_background(request: PlannerRequest, db: AsyncSession):
    """Background task to run the planner and save results to DB."""
    planner = PlannerAgent()
    
    # We could optionally dequeue from redis here, but for simplicity 
    # we just run the agent directly. The queue is mainly for rate limiting.
    try:
        response = await planner.run(request)
        
        # In a full implementation, we'd unpack `response.context` and save everything
        # to their respective tables (jds, candidates, outreach_emails, eval_results)
        # For now, we update the main run status.
        db_run = await db.get(Run, response.run_id)
        if db_run:
            db_run.status = response.status
            from datetime import datetime, timezone
            db_run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
    except Exception as e:
        # Update db run to failed
        pass

@router.post("/run", response_model=RunPipelineResponse)
async def run_pipeline(
    payload: RunPipelineRequest, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # Enqueue task to redis (for durability/scaling, though we run it locally here)
    await task_queue.enqueue(payload.model_dump_json())
    
    # Create the planner request which generates the run_id inside the task graph if needed.
    # Actually, planner creates the run_id inside _build_task_graph. We need the run_id here.
    # Let's create a DB record first.
    db_run = Run(goal_text=payload.goal_text, status="pending")
    db.add(db_run)
    await db.commit()
    await db.refresh(db_run)
    
    request = PlannerRequest(
        run_id=db_run.id,
        goal_text=payload.goal_text,
        raw_jd_text=payload.raw_jd_text,
        top_k=payload.top_k
    )
    
    background_tasks.add_task(execute_pipeline_background, request, db)
    
    return RunPipelineResponse(
        run_id=db_run.id,
        status="pending",
        message="Pipeline execution started in the background."
    )


@router.get("/{run_id}/stream")
async def stream_pipeline_events(run_id: str):
    """
    Server-Sent Events endpoint to stream real-time progress.
    """
    queue = event_emitter.subscribe(run_id)
    
    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield event.to_sse()
                
                if event.event_type in ("run_completed", "error"):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            event_emitter.unsubscribe(run_id, queue)
            
    return EventSourceResponse(event_generator())
