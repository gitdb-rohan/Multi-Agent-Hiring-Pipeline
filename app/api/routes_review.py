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


class ReviewDecision(BaseModel):
    decision: str  # e.g., "approved", "rejected", "edited"
    notes: str | None = None
    reviewer: str = "human"


@router.get("/queue", response_model=List[EvalResultOut])
async def get_review_queue(db: AsyncSession = Depends(get_db)):
    """Fetch all eval results that need human review and haven't been reviewed yet."""
    # Find eval results that need review but don't have a human review entry yet.
    # We do this simply by checking needs_review=True, and maybe doing an outer join.
    query = select(EvalResultDB).where(EvalResultDB.needs_review == True)
    result = await db.execute(query)
    evals = result.scalars().all()
    
    # Simple check for existing review for now - in production this would be an SQL NOT EXISTS
    out = []
    for e in evals:
        # Check if review exists
        rev_query = select(HumanReview).where(HumanReview.eval_result_id == e.id)
        rev_res = await db.execute(rev_query)
        if not rev_res.scalars().first():
            out.append(EvalResultOut(**e.__dict__))
            
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
