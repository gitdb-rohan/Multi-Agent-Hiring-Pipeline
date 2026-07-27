import asyncio
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.infra.db import EvalResultDB, HumanReview, Run, Base

async def test():
    engine = create_async_engine("sqlite+aiosqlite:///app/data/hiring.db")
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as db:
        pending_query = select(EvalResultDB).where(
            EvalResultDB.needs_review == True,
            ~EvalResultDB.id.in_(
                select(HumanReview.eval_result_id)
            )
        )
        res = await db.execute(pending_query)
        evals = res.scalars().all()
        print(f"Pending evals: {len(evals)}")
        
        runs = await db.execute(select(Run))
        print(f"Runs: {[(r.id, r.status) for r in runs.scalars().all()]}")

if __name__ == "__main__":
    asyncio.run(test())
