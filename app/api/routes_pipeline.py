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
    auto_approve: bool = False

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
        "top_k": payload.top_k,
        "auto_approve": payload.auto_approve
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
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(context_obj, "context_data")
        db.add(context_obj)
        await db.commit()
        
    return {"status": "success", "message": "JD updated successfully"}

@router.delete("/{run_id}/candidate/{candidate_id}")
async def remove_candidate_from_run(run_id: str, candidate_id: str, db: AsyncSession = Depends(get_db), hr_email: str = Depends(get_current_hr)):
    """Remove a specific candidate from the pipeline context if rejected by human review."""
    db_run = await db.get(Run, run_id)
    if not db_run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    context_result = await db.execute(select(PipelineContext).where(PipelineContext.run_id == run_id))
    context_obj = context_result.scalars().first()
    
    if context_obj and "scored_candidates" in context_obj.context_data:
        context_data = context_obj.context_data
        candidates = context_data.get("scored_candidates", [])
        
        # Remove candidate
        new_candidates = [c for c in candidates if c.get("candidate_id") != candidate_id]
        context_data["scored_candidates"] = new_candidates
        
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(context_obj, "context_data")
        db.add(context_obj)
        await db.commit()
        
    return {"status": "success", "message": "Candidate removed successfully"}

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


class ContinuePipelineRequest(BaseModel):
    extra_k: int = 0

@router.post("/{run_id}/continue")
async def continue_pipeline(
    run_id: str,
    payload: ContinuePipelineRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    hr_email: str = Depends(get_current_hr)
):
    """Resume a completed or paused pipeline, processing additional candidates."""
    db_run = await db.get(Run, run_id)
    if not db_run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    db_run.status = "running"
    await db.commit()
    
    # Dispatch with extra_k
    background_tasks.add_task(run_pipeline_in_background, db_run.id, payload.extra_k)
    
    return {"status": "success", "message": f"Pipeline continuing with {payload.extra_k} more candidates."}


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

@router.delete("/run/{run_id}")
async def delete_run(run_id: str, hr_email: str = Depends(get_current_hr), db: AsyncSession = Depends(get_db)):
    """Delete a pipeline run and all associated data."""
    db_run = await db.get(Run, run_id)
    if not db_run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    from app.infra.db import TaskState, PipelineContext, ScoredCandidateDB, OutreachEmailDB, EvalResultDB, HumanReview
    from sqlalchemy import delete
    
    # Delete child records
    await db.execute(delete(TaskState).where(TaskState.run_id == run_id))
    await db.execute(delete(PipelineContext).where(PipelineContext.run_id == run_id))
    await db.execute(delete(ScoredCandidateDB).where(ScoredCandidateDB.run_id == run_id))
    await db.execute(delete(OutreachEmailDB).where(OutreachEmailDB.run_id == run_id))
    
    # HumanReview is linked to EvalResultDB, so we need to fetch eval result ids first or join
    evals_res = await db.execute(select(EvalResultDB.id).where(EvalResultDB.run_id == run_id))
    eval_ids = evals_res.scalars().all()
    if eval_ids:
        await db.execute(delete(HumanReview).where(HumanReview.eval_result_id.in_(eval_ids)))
        await db.execute(delete(EvalResultDB).where(EvalResultDB.run_id == run_id))
        
    await db.execute(delete(Run).where(Run.id == run_id))
    await db.commit()
    
    return {"status": "success", "message": f"Run {run_id} deleted."}

@router.get("/{run_id}/emails")
async def get_run_emails(run_id: str, hr_email: str = Depends(get_current_hr), db: AsyncSession = Depends(get_db)):
    """Fetch all emails generated during a pipeline run."""
    from app.infra.db import OutreachEmailDB, CandidateDB
    from sqlalchemy.future import select
    from sqlalchemy.orm import selectinload
    from app.infra.vector_store import vector_store
    
    # query OutreachEmailDB
    stmt = select(OutreachEmailDB).where(OutreachEmailDB.run_id == run_id)
    res = await db.execute(stmt)
    emails = res.scalars().all()
    
    result = []
    for e in emails:
        cand_data = vector_store.get_candidate(e.candidate_id)
        cand_name = cand_data["metadata"].get("name", e.candidate_id) if cand_data else e.candidate_id
        cand_email = cand_data["metadata"].get("email", "Unknown Email") if cand_data else "Unknown Email"
        result.append({
            "id": e.id, 
            "candidate_id": e.candidate_id, 
            "candidate_name": cand_name,
            "candidate_email": cand_email,
            "subject": e.subject, 
            "body": e.body, 
            "status": e.status
        })
    return result
@router.get("/runs")
async def get_all_runs(hr_email: str = Depends(get_current_hr), db: AsyncSession = Depends(get_db)):
    """Fetch all pipeline runs."""
    from sqlalchemy.future import select
    stmt = select(Run).order_by(Run.created_at.desc())
    res = await db.execute(stmt)
    runs = res.scalars().all()
    
    return [
        {
            "id": r.id,
            "goal_text": r.goal_text,
            "status": r.status,
            "created_at": r.created_at,
            "completed_at": r.completed_at
        }
        for r in runs
    ]
