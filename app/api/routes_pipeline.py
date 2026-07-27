import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import logging

from app.orchestration.events import event_emitter
from app.infra.db import Run, PipelineContext
from app.dependencies import get_db
from app.api.auth import get_current_hr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.worker import run_pipeline_in_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

class RunPipelineRequest(BaseModel):
    goal_text: str
    raw_jd_text: str
    top_k: int = 5

class RunPipelineResponse(BaseModel):
    run_id: str
    status: str
    message: str

@router.post("/run", response_model=RunPipelineResponse)
async def run_pipeline(
    payload: RunPipelineRequest, 
    background_tasks: BackgroundTasks,
    hr_email: str = Depends(get_current_hr),
    db: AsyncSession = Depends(get_db)
):
    db_run = Run(goal_text=payload.goal_text, status="pending", created_by=hr_email)
    db.add(db_run)
    await db.commit()
    await db.refresh(db_run)
    
    # Save initial context
    context_data = {
        "hr_email": hr_email,
        "raw_jd_text": payload.raw_jd_text,
        "top_k": payload.top_k
    }
    context_obj = PipelineContext(run_id=db_run.id, context_data=context_data)
    db.add(context_obj)
    await db.commit()
    
    # Trigger background worker
    background_tasks.add_task(run_pipeline_in_background, db_run.id)
    
    return RunPipelineResponse(
        run_id=db_run.id,
        status="pending",
        message="Pipeline execution started in the background."
    )

@router.get("/{run_id}/state")
async def get_pipeline_state(run_id: str, db: AsyncSession = Depends(get_db), hr_email: str = Depends(get_current_hr)):
    """Fetch the current DAG state and outputs."""
    db_run = await db.get(Run, run_id)
    if not db_run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    context_result = await db.execute(select(PipelineContext).where(PipelineContext.run_id == run_id))
    context_obj = context_result.scalars().first()
    context = context_obj.context_data if context_obj else {}
    
    return {
        "run_id": run_id,
        "status": db_run.status,
        "context": context
    }

class EditJDRequest(BaseModel):
    extracted_jd: dict

@router.put("/{run_id}/jd")
async def edit_extracted_jd(run_id: str, req: EditJDRequest, db: AsyncSession = Depends(get_db), hr_email: str = Depends(get_current_hr)):
    """Allow HR to manually edit the extracted JD payload."""
    db_run = await db.get(Run, run_id)
    if not db_run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    if db_run.status != "paused_for_review":
        raise HTTPException(status_code=400, detail="Pipeline is not paused for review")
        
    context_result = await db.execute(select(PipelineContext).where(PipelineContext.run_id == run_id))
    context_obj = context_result.scalars().first()
    
    if context_obj:
        context_data = context_obj.context_data
        context_data["extracted_jd"] = req.extracted_jd
        context_obj.context_data = context_data
        
        # Also need to invalidate caching for downstream tasks or just let it proceed
        # For simplicity, we just update context
        db.add(context_obj)
        await db.commit()
        
    return {"status": "success", "message": "JD updated successfully"}

@router.post("/{run_id}/resume")
async def resume_pipeline(
    run_id: str, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db), 
    hr_email: str = Depends(get_current_hr)
):
    """Explicitly unpause the pipeline and trigger the next task tier."""
    db_run = await db.get(Run, run_id)
    if not db_run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    if db_run.status != "paused_for_review":
        raise HTTPException(status_code=400, detail="Pipeline is not paused for review")
        
    db_run.status = "running"
    await db.commit()
    
    # Resume by dispatching again
    background_tasks.add_task(run_pipeline_in_background, db_run.id)
    
    return {"status": "success", "message": "Pipeline resumed"}

@router.get("/{run_id}/stream")
async def stream_pipeline_events(run_id: str, hr_email: str = Depends(get_current_hr)):
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
