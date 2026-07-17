import hashlib
from pydantic import BaseModel, Field


def generate_candidate_id(email: str) -> str:
    """Generate a deterministic candidate ID from email for dedup.
    
    Same email always produces the same ID, so ChromaDB's upsert
    automatically replaces the old entry when a candidate re-submits.
    """
    return f"cand_{hashlib.md5(email.lower().strip().encode()).hexdigest()[:12]}"


class CandidateProfile(BaseModel):
    id: str = Field(default="", description="Deterministic ID derived from email (set by ingestion)")
    name: str = Field(description="Candidate's full name")
    email: str = Field(default="", description="Candidate's email address (used as dedup key)")
    current_title: str = Field(description="Candidate's current job title")
    skills: list[str] = Field(description="List of skills the candidate possesses")
    years_of_experience: int = Field(description="Total years of professional experience")
    previous_companies: list[str] = Field(default_factory=list, description="List of previous companies")
    projects: list[str] = Field(default_factory=list, description="Notable projects or achievements")
    position_applied: str = Field(default="", description="Position the candidate applied for")
    summary: str = Field(description="A brief summary or bio of the candidate")

    def to_embedding_text(self) -> str:
        """Build the text representation used for generating vector embeddings."""
        parts = [f"{self.current_title}. Skills: {', '.join(self.skills)}. {self.summary}"]
        if self.projects:
            parts.append(f"Projects: {', '.join(self.projects)}")
        if self.previous_companies:
            parts.append(f"Experience at: {', '.join(self.previous_companies)}")
        return " ".join(parts)

    def to_chroma_metadata(self) -> dict:
        """Build metadata dict for ChromaDB. Values must be str/int/float — no lists."""
        return {
            "name": self.name,
            "email": self.email,
            "years_of_experience": self.years_of_experience,
            "previous_companies": ",".join(self.previous_companies),
            "projects": ",".join(self.projects),
            "position_applied": self.position_applied,
        }

class ScoredCandidate(BaseModel):
    candidate_id: str
    semantic_similarity: float = Field(description="Raw vector search score (0.0 to 1.0)")
    llm_rerank_score: float = Field(description="LLM evaluation score (0.0 to 1.0)")
    final_score: float = Field(description="Combined or final score used for sorting")
    matched_skills: list[str] = Field(description="Skills from JD that the candidate has")
    missing_skills: list[str] = Field(description="Skills from JD that the candidate is missing")
    rationale: str = Field(description="Brief explanation of why the candidate received this score")
