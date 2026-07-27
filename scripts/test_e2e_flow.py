import asyncio
import os
import sys

# Ensure app is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# We need to set dummy keys for LLM so it doesn't crash on init if they are empty
os.environ["OPENAI_API_KEY"] = "sk-mock-key"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-mock-key"
os.environ["GEMINI_API_KEY"] = "mock-gemini-key"

from app.config import settings

# Patch database url BEFORE importing anything that creates the engine
db_url = "sqlite+aiosqlite:///test.db"
settings.DATABASE_URL = db_url

from app.main import app
from app.infra.db import Base, HRUser
from app.api.auth import hash_password, create_access_token

async def run_test():
    print("Initializing test database...")
    engine = create_async_engine(db_url, echo=False)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        async with async_session_maker() as session:
            email = "test_hr@example.com"
            user = HRUser(email=email, hashed_password=hash_password("password"))
            session.add(user)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
    except Exception as e:
        print(f"Failed to initialize DB: {e}. Is postgres running?")
        return
            
    token = create_access_token({"sub": email})
    headers = {"Authorization": f"Bearer {token}"}
    
    # Use ASGITransport to talk directly to the FastAPI app in memory
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        print("\n--- Test 1: Ingest Candidate ---")
        resp = await client.post("/candidates/ingest/manual", json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "current_title": "Senior Backend Engineer",
            "skills": "Python, FastAPI, SQLAlchemy",
            "years_of_experience": 10.0,
            "resume_text": "Experienced software engineer with 10 years of Python.",
            "position_applied": "Senior Backend Engineer"
        }, headers=headers)
        
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
        if resp.status_code != 200:
            print("Ingestion failed.")
            return
            
        candidate_id = resp.json().get("candidate_id")
        
        print("\n--- Test 2: List Candidates ---")
        resp = await client.get("/candidates/", headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            print("List candidates failed.")
            return
            
        candidates = resp.json()
        print(f"Found {len(candidates)} candidates.")
        
        print("\n--- Test 3: Trigger Pipeline ---")
        resp = await client.post("/pipeline/run", json={
            "goal_text": "Find a backend engineer",
            "raw_jd_text": "Looking for a senior Python backend developer.",
            "top_k": 5
        }, headers=headers)
        
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
        if resp.status_code != 200:
            print("Pipeline trigger failed.")
            return
            
        run_id = resp.json().get("run_id")
        
        print("\n--- Test 4: Check Pipeline State ---")
        resp = await client.get(f"/pipeline/{run_id}/state", headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
        if resp.status_code != 200:
            print("State fetch failed.")
            return
        
    print("\nEnd-to-End Integration Test Completed Successfully!")

if __name__ == "__main__":
    asyncio.run(run_test())
