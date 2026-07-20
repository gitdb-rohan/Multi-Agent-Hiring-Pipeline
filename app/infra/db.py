from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

# Async session factory
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Base class for SQLAlchemy models
Base = declarative_base()

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async db session"""
    async with async_session_maker() as session:
        yield session

# --- Models ---
from sqlalchemy import Column, String, Float, Boolean, DateTime, Integer, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class HRUser(Base):
    __tablename__ = "hr_users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    auth_token = Column(String, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())

class Run(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True, default=generate_uuid)
    goal_text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

class JobDescription(Base):
    __tablename__ = "jds"
    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    raw_text = Column(Text, nullable=False)
    extracted_json = Column(JSON, nullable=False)
    confidence = Column(Float, nullable=False)

class ScoredCandidateDB(Base):
    __tablename__ = "scored_candidates"
    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    candidate_id = Column(String, nullable=False)
    semantic_similarity = Column(Float, nullable=False, default=0.0)
    llm_rerank_score = Column(Float, nullable=False, default=0.0)
    final_score = Column(Float, nullable=False)
    matched_skills_json = Column(JSON, nullable=False, default=list)
    missing_skills_json = Column(JSON, nullable=False, default=list)
    rationale_json = Column(JSON, nullable=False)

class OutreachEmailDB(Base):
    __tablename__ = "outreach_emails"
    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    candidate_id = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="pending")

class EvalResultDB(Base):
    __tablename__ = "eval_results"
    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    agent = Column(String, nullable=False)
    task_id = Column(String, nullable=False)
    relevance = Column(Float, nullable=False)
    faithfulness = Column(Float, nullable=False)
    completeness = Column(Float, nullable=False)
    needs_review = Column(Boolean, default=False)
    review_reason = Column(String, nullable=True)

class HumanReview(Base):
    __tablename__ = "human_reviews"
    id = Column(String, primary_key=True, default=generate_uuid)
    eval_result_id = Column(String, ForeignKey("eval_results.id"), nullable=False)
    reviewer = Column(String, nullable=True)
    decision = Column(String, nullable=True) # e.g. "approved", "rejected"
    notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
