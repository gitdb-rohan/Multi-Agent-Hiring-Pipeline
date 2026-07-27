from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.infra.db import EvalResultDB, HumanReview
from app.dependencies import get_db
from app.api.auth import get_current_hr

router = APIRouter(prefix="/review", tags=["review"])


class EvalResultOut(BaseModel):
    id: str
    run_id: str
    agent: str
    task_id: str
    relevance: float
    faithfulness: float
    completeness: float
    needs_review: bool
    review_reason: str | None
    context_data: list | None = None


class EmailUpdateRequest(BaseModel):
    subject: str
    body: str

class ReviewDecision(BaseModel):
    decision: str  # e.g., "approved", "rejected", "edited"
    notes: str | None = None
    reviewer: str = "human"


@router.get("/queue", response_model=List[EvalResultOut])
async def get_review_queue(db: AsyncSession = Depends(get_db), hr_email: str = Depends(get_current_hr)):
    """Fetch all eval results that need human review and haven't been reviewed yet."""
    from app.infra.db import ScoredCandidateDB, OutreachEmailDB
    # Find eval results that need review but don't have a human review entry yet.
    query = select(EvalResultDB).where(EvalResultDB.needs_review == True)
    result = await db.execute(query)
    evals = result.scalars().all()
    
    out = []
    for e in evals:
        # Check if review exists
        rev_query = select(HumanReview).where(HumanReview.eval_result_id == e.id)
        rev_res = await db.execute(rev_query)
        if not rev_res.scalars().first():
            out_dict = e.__dict__.copy()
            out_dict.pop("_sa_instance_state", None)
            
            # Attach context data based on agent
            context_data = []
            from app.infra.db import PipelineContext
            from app.infra.vector_store import vector_store
            
            pc_query = select(PipelineContext).where(PipelineContext.run_id == e.run_id)
            pc_res = await db.execute(pc_query)
            pc_obj = pc_res.scalars().first()
            
            if pc_obj and pc_obj.context_data:
                if e.agent == "JDAnalyser":
                    if "extracted_jd" in pc_obj.context_data:
                        context_data.append(pc_obj.context_data["extracted_jd"])
                elif e.agent == "CandidateScorer":
                    scored_candidates = pc_obj.context_data.get("scored_candidates", [])
                    for c in scored_candidates:
                        cand_id = c.get("candidate_id")
                        cand_data = vector_store.get_candidate(cand_id)
                        cand_name = cand_data["metadata"].get("name", "Unknown Candidate") if cand_data else "Unknown Candidate"
                        context_data.append({
                            "candidate_id": cand_id,
                            "candidate_name": cand_name,
                            "final_score": c.get("final_score"),
                            "rationale": {
                                "matched_skills": c.get("matched_skills"),
                                "missing_skills": c.get("missing_skills"),
                                "reasoning": c.get("rationale")
                            }
                        })
                elif e.agent == "OutreachDrafter":
                    emails = pc_obj.context_data.get("outreach_emails", [])
                    for em in emails:
                        cand_id = em.get("candidate_id")
                        cand_data = vector_store.get_candidate(cand_id)
                        cand_name = cand_data["metadata"].get("name", "Unknown Candidate") if cand_data else "Unknown Candidate"
                        cand_email = cand_data["metadata"].get("email", "Unknown Email") if cand_data else "Unknown Email"
                        context_data.append({
                            "id": f"{e.run_id}_{cand_id}",
                            "candidate_id": cand_id,
                            "candidate_name": cand_name,
                            "candidate_email": cand_email,
                            "subject": em.get("subject"),
                            "body": em.get("body")
                        })
            
            out_dict["context_data"] = context_data
            out.append(EvalResultOut(**out_dict))
            
    return out

@router.delete("/email/{email_id}")
async def delete_email(email_id: str, db: AsyncSession = Depends(get_db), hr_email: str = Depends(get_current_hr)):
    """Delete a drafted email (e.g. if HR rejects this specific candidate's outreach)."""
    from app.infra.db import PipelineContext
    from fastapi import HTTPException
    
    # email_id is in format {run_id}_{candidate_id}
    parts = email_id.split("_", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid email ID format")
    run_id, candidate_id = parts[0], parts[1]
    
    pc_query = select(PipelineContext).where(PipelineContext.run_id == run_id)
    pc_res = await db.execute(pc_query)
    pc_obj = pc_res.scalars().first()
    
    if pc_obj and "outreach_emails" in pc_obj.context_data:
        emails = pc_obj.context_data["outreach_emails"]
        # Find the email
        for i, em in enumerate(emails):
            if em.get("candidate_id") == candidate_id:
                emails.pop(i)
                pc_obj.context_data["outreach_emails"] = emails
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(pc_obj, "context_data")
                db.add(pc_obj)
                await db.commit()
                return {"status": "success", "message": "Email removed successfully"}
    
    raise HTTPException(status_code=404, detail="Email not found")


@router.put("/email/{email_id}")
async def update_email(
    email_id: str,
    update_data: EmailUpdateRequest,
    db: AsyncSession = Depends(get_db),
    hr_email: str = Depends(get_current_hr)
):
    """Update the subject and body of a drafted email before approval."""
    from app.infra.db import PipelineContext
    from fastapi import HTTPException
    
    parts = email_id.split("_", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid email ID format")
    run_id, candidate_id = parts[0], parts[1]
    
    pc_query = select(PipelineContext).where(PipelineContext.run_id == run_id)
    pc_res = await db.execute(pc_query)
    pc_obj = pc_res.scalars().first()
    
    if not pc_obj or not pc_obj.context_data:
        raise HTTPException(status_code=404, detail="Pipeline context not found")
        
    emails = pc_obj.context_data.get("outreach_emails", [])
    updated = False
    for em in emails:
        if em.get("candidate_id") == candidate_id:
            em["subject"] = update_data.subject
            em["body"] = update_data.body
            updated = True
            break
            
    if not updated:
        raise HTTPException(status_code=404, detail="Email not found")
        
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(pc_obj, "context_data")
    db.add(pc_obj)
    await db.commit()
    return {"status": "success", "message": "Email updated successfully"}


@router.post("/{eval_id}/submit")
async def submit_review(
    eval_id: str, 
    decision: ReviewDecision,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    hr_email: str = Depends(get_current_hr)
):
    """Submit a human review decision for an evaluation result."""
    eval_res = await db.get(EvalResultDB, eval_id)
    if not eval_res:
        raise HTTPException(status_code=404, detail="Eval result not found")
        
    review = HumanReview(
        eval_result_id=eval_id,
        reviewer=decision.reviewer,
        decision=decision.decision,
        notes=decision.notes,
    )
    from datetime import datetime, timezone
    review.reviewed_at = datetime.now(timezone.utc)
    
    db.add(review)
    await db.commit()
    
    if decision.decision == "rejected":
        # Terminate the pipeline run immediately
        db_run = await db.get(Run, eval_res.run_id)
        if db_run:
            db_run.status = "failed"
            await db.commit()
            from app.orchestration.events import event_emitter
            await event_emitter.emit_error(db_run.id, f"Pipeline terminated due to rejected review for agent: {eval_res.agent}")
            
        return {"status": "success", "message": "Review rejected. Pipeline terminated."}

    # Check if there are any pending reviews for this run
    from app.infra.db import Run
    pending_query = select(EvalResultDB).where(
        EvalResultDB.run_id == eval_res.run_id,
        EvalResultDB.needs_review == True,
        ~EvalResultDB.id.in_(
            select(HumanReview.eval_result_id)
        )
    )
    pending_res = await db.execute(pending_query)
    pending_evals = pending_res.scalars().all()
    
    if len(pending_evals) == 0:
        db_run = await db.get(Run, eval_res.run_id)
        if db_run and db_run.status in ["paused_for_review", "needs_review"]:
            db_run.status = "running"
            await db.commit()
            from app.worker import run_pipeline_in_background
            background_tasks.add_task(run_pipeline_in_background, db_run.id)
    
    return {"status": "success", "message": "Review submitted successfully."}


class EmailDecision(BaseModel):
    decision: str  # "approved", "rejected"
    edited_body: str | None = None
    reviewer_email: str

@router.post("/email/{email_id}/decision")
async def review_single_email(
    email_id: str,
    decision: EmailDecision,
    db: AsyncSession = Depends(get_db),
    hr_email: str = Depends(get_current_hr)
):
    from app.infra.db import OutreachEmailDB
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from contextlib import AsyncExitStack
    import os
    
    email_record = await db.get(OutreachEmailDB, email_id)
    if not email_record:
        raise HTTPException(status_code=404, detail="Email not found")
        
    
    if decision.decision == "approved":
        body_to_send = decision.edited_body if decision.edited_body else email_record.body
        email_record.body = body_to_send
        
        # HTML Wrapper
        html_body = f"""
        <html>
        <head></head>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="padding: 20px;">
                {body_to_send}
            </div>
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 0.9em; color: #777;">
                <img src="https://example.com/logo.png" alt="Company Logo" style="height: 30px; margin-bottom: 10px;"><br>
                <strong>HireFlow Recruiting Team</strong><br>
                <a href="#">Privacy Policy</a> | <a href="#">Careers</a>
            </div>
        </body>
        </html>
        """
        
        # Send via MCP
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
                    "candidate_id": email_record.candidate_id,
                    "subject": email_record.subject,
                    "body": html_body
                }
            )

            
        email_record.status = "sent"
        # We could also log this to HumanReview if we wanted granular tracking
    else:
        email_record.status = "rejected"
        
    await db.commit()
    return {"status": "success", "email_id": email_id, "new_status": email_record.status}
