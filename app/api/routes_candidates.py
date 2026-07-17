"""
API routes for candidate ingestion and management.
Supports single file upload, batch upload, and folder-based ingestion.
"""
import os
import logging
import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List

from app.ingestion.resume_parser import extract_text_from_file, is_supported_resume
from app.ingestion.profile_extractor import extract_profile_from_resume
from app.infra.vector_store import vector_store
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["candidates"])


# --- Response models ---

class IngestResult(BaseModel):
    candidate_id: str
    name: str
    email: str
    status: str  # "ingested" or "error"
    message: str = ""


class IngestResponse(BaseModel):
    total: int
    ingested: int
    errors: int
    results: List[IngestResult]


class CandidateOut(BaseModel):
    id: str
    name: str
    email: str
    current_title: str
    skills: list[str]
    years_of_experience: int
    previous_companies: list[str]
    projects: list[str]
    position_applied: str
    summary: str


class FolderIngestRequest(BaseModel):
    folder_path: str = Field(description="Absolute path to a folder containing resume files")
    position_applied: str = Field(default="", description="Position all candidates in this batch are applying for")


class CandidateManualInput(BaseModel):
    name: str = Field(description="Candidate's full name")
    email: str = Field(description="Candidate's email address")
    current_title: str = Field(description="Current job title")
    skills: str = Field(description="Comma-separated list of skills")
    years_of_experience: int = Field(description="Total years of experience")
    previous_companies: str = Field(default="", description="Comma-separated list of companies")
    projects: str = Field(default="", description="Comma-separated list of projects")
    summary: str = Field(default="", description="Brief professional summary")
    position_applied: str = Field(default="", description="Position applied for")


# --- Helpers ---

async def _ingest_single_file(
    file_path: str, 
    position_applied: str = "",
) -> IngestResult:
    """
    Core ingestion logic: parse → extract profile → upsert to ChromaDB.
    Returns an IngestResult with status.
    """
    try:
        # 1. Extract text from resume
        raw_text = extract_text_from_file(file_path)
        if not raw_text.strip():
            return IngestResult(
                candidate_id="", name="", email="",
                status="error", message=f"No text could be extracted from {file_path}"
            )

        # 2. LLM extracts structured profile
        profile = await extract_profile_from_resume(raw_text, position_applied)

        # 3. Upsert to ChromaDB (dedup by deterministic ID from email)
        vector_store.upsert_candidate(
            candidate_id=profile.id,
            document=profile.to_embedding_text(),
            metadata=profile.to_chroma_metadata(),
        )

        return IngestResult(
            candidate_id=profile.id,
            name=profile.name,
            email=profile.email,
            status="ingested",
            message=f"Successfully ingested (ID: {profile.id})",
        )

    except Exception as e:
        logger.error(f"Failed to ingest {file_path}: {e}")
        return IngestResult(
            candidate_id="", name="", email="",
            status="error", message=str(e),
        )


# --- Endpoints ---

@router.post("/ingest", response_model=IngestResponse)
async def ingest_resume(
    file: UploadFile = File(...),
    position_applied: str = Query(default="", description="Position the candidate is applying for"),
):
    """
    Upload a single resume (PDF/DOCX). Extracts profile via LLM, deduplicates 
    by email, and upserts to the vector database.
    
    If a candidate with the same email already exists, their profile is updated 
    (not duplicated).
    """
    if not file.filename or not is_supported_resume(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Upload a PDF or DOCX file.",
        )

    # Save uploaded file to a temp location
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await _ingest_single_file(tmp_path, position_applied)
        return IngestResponse(
            total=1,
            ingested=1 if result.status == "ingested" else 0,
            errors=1 if result.status == "error" else 0,
            results=[result],
        )
    finally:
        os.unlink(tmp_path)


@router.post("/ingest/batch", response_model=IngestResponse)
async def ingest_batch(
    files: List[UploadFile] = File(...),
    position_applied: str = Query(default="", description="Position candidates are applying for"),
):
    """
    Upload multiple resumes at once. Each file is processed independently.
    Returns per-file results.
    """
    results: List[IngestResult] = []

    for file in files:
        if not file.filename or not is_supported_resume(file.filename):
            results.append(IngestResult(
                candidate_id="", name="", email="",
                status="error",
                message=f"Unsupported file type: {file.filename}",
            ))
            continue

        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            result = await _ingest_single_file(tmp_path, position_applied)
            results.append(result)
        finally:
            os.unlink(tmp_path)

    ingested = sum(1 for r in results if r.status == "ingested")
    return IngestResponse(
        total=len(results),
        ingested=ingested,
        errors=len(results) - ingested,
        results=results,
    )


@router.post("/ingest/folder", response_model=IngestResponse)
async def ingest_from_folder(payload: FolderIngestRequest):
    """
    Process all resume files (PDF/DOCX) in a local folder.
    Useful for bulk-importing an existing candidate pool.
    """
    folder = Path(payload.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {payload.folder_path}")

    resume_files = [
        str(f) for f in folder.iterdir()
        if f.is_file() and is_supported_resume(str(f))
    ]

    if not resume_files:
        raise HTTPException(status_code=400, detail=f"No PDF/DOCX files found in {payload.folder_path}")

    results: List[IngestResult] = []
    for file_path in resume_files:
        result = await _ingest_single_file(file_path, payload.position_applied)
        results.append(result)

    ingested = sum(1 for r in results if r.status == "ingested")
    return IngestResponse(
        total=len(results),
        ingested=ingested,
        errors=len(results) - ingested,
        results=results,
    )


@router.post("/ingest/manual", response_model=IngestResult)
async def ingest_manual(candidate: CandidateManualInput):
    """
    Manually ingest a candidate without a resume file.
    """
    try:
        from app.schemas.candidate import CandidateProfile
        
        # Build CandidateProfile
        profile = CandidateProfile(
            name=candidate.name,
            email=candidate.email,
            current_title=candidate.current_title,
            skills=[s.strip() for s in candidate.skills.split(",") if s.strip()],
            years_of_experience=candidate.years_of_experience,
            previous_companies=[c.strip() for c in candidate.previous_companies.split(",") if c.strip()],
            projects=[p.strip() for p in candidate.projects.split(",") if p.strip()],
            summary=candidate.summary,
            position_applied=candidate.position_applied
        )
        
        # Generate ID (dedup key)
        from app.schemas.candidate import generate_candidate_id
        profile.id = generate_candidate_id(profile.email)
        
        # Upsert
        vector_store.upsert_candidate(
            candidate_id=profile.id,
            document=profile.to_embedding_text(),
            metadata=profile.to_chroma_metadata(),
        )
        
        return IngestResult(
            candidate_id=profile.id,
            name=profile.name,
            email=profile.email,
            status="ingested",
            message=f"Successfully ingested (ID: {profile.id})"
        )
    except Exception as e:
        logger.error(f"Manual ingest failed: {e}")
        return IngestResult(
            candidate_id="", name="", email="",
            status="error", message=str(e)
        )


@router.get("/", response_model=List[CandidateOut])
async def list_candidates(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    List all candidates currently in the vector store with pagination.
    Retrieves from ChromaDB (the source of truth for candidate profiles).
    """
    # ChromaDB's get() with no IDs returns all documents
    all_results = vector_store.collection.get(
        include=["documents", "metadatas"],
        limit=limit,
        offset=skip,
    )

    candidates = []
    if all_results and all_results["ids"]:
        for i, cid in enumerate(all_results["ids"]):
            meta = all_results["metadatas"][i] if all_results["metadatas"] else {}
            doc = all_results["documents"][i] if all_results["documents"] else ""

            candidates.append(CandidateOut(
                id=cid,
                name=meta.get("name", ""),
                email=meta.get("email", ""),
                current_title="",  # Not stored separately in metadata
                skills=[],  # Extracted from document text, not stored separately
                years_of_experience=meta.get("years_of_experience", 0),
                previous_companies=meta.get("previous_companies", "").split(",") if meta.get("previous_companies") else [],
                projects=meta.get("projects", "").split(",") if meta.get("projects") else [],
                position_applied=meta.get("position_applied", ""),
                summary=doc[:200] if doc else "",
            ))

    return candidates


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: str):
    """Get a single candidate's full profile by ID."""
    result = vector_store.get_candidate(candidate_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")

    meta = result.get("metadata", {})
    doc = result.get("document", "")

    return CandidateOut(
        id=result["id"],
        name=meta.get("name", ""),
        email=meta.get("email", ""),
        current_title="",
        skills=[],
        years_of_experience=meta.get("years_of_experience", 0),
        previous_companies=meta.get("previous_companies", "").split(",") if meta.get("previous_companies") else [],
        projects=meta.get("projects", "").split(",") if meta.get("projects") else [],
        position_applied=meta.get("position_applied", ""),
        summary=doc[:200] if doc else "",
    )
