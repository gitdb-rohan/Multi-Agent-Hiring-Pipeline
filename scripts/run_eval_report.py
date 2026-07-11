import asyncio
import argparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.infra.db import get_db_session, EvalResultDB

async def run_report():
    async for db in get_db_session():
        print("=== Pipeline Evaluation Report ===")
        
        # Total evals
        result = await db.execute(select(func.count(EvalResultDB.id)))
        total_evals = result.scalar()
        print(f"Total Evaluations: {total_evals}")
        
        if total_evals == 0:
            return
            
        # Needs review
        result = await db.execute(select(func.count(EvalResultDB.id)).where(EvalResultDB.needs_review == True))
        needs_review = result.scalar()
        print(f"Flagged for Human Review: {needs_review} ({needs_review/total_evals*100:.1f}%)")
        
        # Averages by agent
        result = await db.execute(
            select(
                EvalResultDB.agent, 
                func.avg(EvalResultDB.relevance),
                func.avg(EvalResultDB.faithfulness),
                func.avg(EvalResultDB.completeness)
            ).group_by(EvalResultDB.agent)
        )
        
        print("\n--- Average Scores by Agent ---")
        for row in result.all():
            agent, rel, faith, comp = row
            print(f"{agent}: Relevance={rel:.2f}, Faithfulness={faith:.2f}, Completeness={comp:.2f}")

        break # only need one session

if __name__ == "__main__":
    asyncio.run(run_report())
