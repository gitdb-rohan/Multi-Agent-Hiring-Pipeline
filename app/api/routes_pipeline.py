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
from app.api.auth import get_current_hr
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
        response = await planner.run(request, initial_context={'hr_email': hr_email})
        
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

class DraftOutreachRequest(BaseModel):
    candidate_email: str
    intent: str
    custom_instructions: str = ""
    
@router.post("/emails/draft")
async def draft_outreach_email(
    req: DraftOutreachRequest,
    hr_email: str = Depends(get_current_hr)
):
    from app.agents.outreach_drafter import OutreachDrafter, OutreachDrafterRequest
    from app.schemas.jd import ExtractedJD
    from app.schemas.candidate import ScoredCandidate, generate_candidate_id
    from app.infra.vector_store import vector_store
    
    # 1. Generate cand_id
    cand_id = generate_candidate_id(req.candidate_email)
    
    # 2. Try to fetch candidate name from Chroma
    cand_name = "Candidate"
    cand_data = vector_store.get_candidate(cand_id)
    if cand_data and "name" in cand_data["metadata"]:
        cand_name = cand_data["metadata"]["name"]
        
    # 3. Create fake JD to carry intent + custom instructions
    role_str = f"Intent: {req.intent}"
    if req.custom_instructions:
        role_str += f"\nCustom Instructions: {req.custom_instructions}"
        
    fake_jd = ExtractedJD(role=role_str, required_skills=[], nice_to_have_skills=[])
    fake_candidate = ScoredCandidate(
        candidate_id=cand_id, 
        final_score=1.0, 
        semantic_similarity=1.0,
        llm_rerank_score=1.0,
        matched_skills=[],
        missing_skills=[],
        rationale=f"Manual draft requested for {cand_name} ({req.candidate_email})."
    )
    
    drafter = OutreachDrafter()
    drafter_req = OutreachDrafterRequest(jd=fake_jd, scored_candidates=[fake_candidate])
    
    # We pass the candidate name inside the context so Drafter can use it
    resp = await drafter.run(drafter_req, context={"hr_email": hr_email, "cand_name": cand_name})
    
    # We don't save to DB here, we just return the draft to the frontend!
    if not resp.emails:
        return {"status": "error", "detail": "Failed to draft email"}
        
    draft = resp.emails[0]
    return {
        "status": "success", 
        "subject": draft.subject,
        "body": draft.body,
        "candidate_id": cand_id,
        "candidate_email": req.candidate_email
    }

class SendManualRequest(BaseModel):
    candidate_email: str
    subject: str
    body: str

@router.post("/emails/send_manual")
async def send_manual_email(req: SendManualRequest, hr_email: str = Depends(get_current_hr)):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from contextlib import AsyncExitStack
    import os
    
    html_body = f"""
    <html>
    <head></head>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="padding: 20px;">
            {req.body}
        </div>
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 0.9em; color: #777;">
            <img src="https://example.com/logo.png" alt="Company Logo" style="height: 30px; margin-bottom: 10px;"><br>
            <strong>HireFlow Recruiting Team</strong><br>
            <a href="#">Privacy Policy</a> | <a href="#">Careers</a>
        </div>
    </body>
    </html>
    """
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "app.mcp_servers.email_server.server"],
        env={**os.environ}
    )
    
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        
        await session.call_tool(
            name="send_outreach_email",
            arguments={
                "candidate_id": req.candidate_email,
                "subject": req.subject,
                "body": html_body
            }
        )
        
    return {"status": "success", "message": "Email sent successfully."}
