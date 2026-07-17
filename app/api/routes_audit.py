from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from pydantic import BaseModel

from app.infra.db import Run, HumanReview, JobDescription
from app.dependencies import get_db

router = APIRouter(prefix="/audit", tags=["audit"])

class AuditLogOut(BaseModel):
    run_id: str
    created_by: str | None
    goal_text: str
    jd_summary: str | None
    decisions: List[dict]

@router.get("/", response_model=List[AuditLogOut])
async def get_audit_log(db: AsyncSession = Depends(get_db)):
    # Fetch all runs ordered by created_at desc
    run_query = select(Run).order_by(Run.created_at.desc())
    runs = (await db.execute(run_query)).scalars().all()
    
    out = []
    for run in runs:
        # Fetch JD
        jd_query = select(JobDescription).where(JobDescription.run_id == run.id)
        jd = (await db.execute(jd_query)).scalars().first()
        jd_summary = jd.extracted_json.get("role", "Unknown Role") if jd else None
        
        # Fetch decisions (joining through EvalResultDB)
        from app.infra.db import EvalResultDB
        rev_query = (
            select(HumanReview, EvalResultDB)
            .join(EvalResultDB, HumanReview.eval_result_id == EvalResultDB.id)
            .where(EvalResultDB.run_id == run.id)
        )
        revs = (await db.execute(rev_query)).all()
        
        decisions = [
            {
                "reviewer": r[0].reviewer,
                "decision": r[0].decision,
                "notes": r[0].notes,
                "agent": r[1].agent,
                "reviewed_at": r[0].reviewed_at.isoformat() if r[0].reviewed_at else None
            }
            for r in revs
        ]
        
        out.append(AuditLogOut(
            run_id=run.id,
            created_by=run.created_by,
            goal_text=run.goal_text,
            jd_summary=jd_summary,
            decisions=decisions
        ))
        
    return out
