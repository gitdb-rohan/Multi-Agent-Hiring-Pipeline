from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.infra.db import EvalResultDB, HumanReview
from app.dependencies import get_db

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


class ReviewDecision(BaseModel):
    decision: str  # e.g., "approved", "rejected", "edited"
    notes: str | None = None
    reviewer: str = "human"


@router.get("/queue", response_model=List[EvalResultOut])
async def get_review_queue(db: AsyncSession = Depends(get_db)):
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
            if e.agent == "CandidateScorer":
                c_query = select(ScoredCandidateDB).where(ScoredCandidateDB.run_id == e.run_id)
                c_res = await db.execute(c_query)
                candidates = c_res.scalars().all()
                for c in candidates:
                    context_data.append({
                        "candidate_id": c.candidate_id,
                        "final_score": c.final_score,
                        "rationale": c.rationale_json
                    })
            elif e.agent == "OutreachDrafter":
                em_query = select(OutreachEmailDB).where(OutreachEmailDB.run_id == e.run_id)
                em_res = await db.execute(em_query)
                emails = em_res.scalars().all()
                for em in emails:
                    context_data.append({
                        "candidate_id": em.candidate_id,
                        "subject": em.subject,
                        "body": em.body
                    })
            
            out_dict["context_data"] = context_data
            out.append(EvalResultOut(**out_dict))
            
    return out


@router.post("/{eval_id}/submit")
async def submit_review(
    eval_id: str, 
    decision: ReviewDecision,
    db: AsyncSession = Depends(get_db)
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
    
    return {"status": "success", "message": "Review submitted successfully."}


class EmailDecision(BaseModel):
    decision: str  # "approved", "rejected"
    edited_body: str | None = None
    reviewer_email: str

@router.post("/email/{email_id}/decision")
async def review_single_email(
    email_id: str,
    decision: EmailDecision,
    db: AsyncSession = Depends(get_db)
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
