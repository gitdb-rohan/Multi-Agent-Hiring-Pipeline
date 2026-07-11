from pydantic import BaseModel, Field

class CandidateProfile(BaseModel):
    id: str = Field(description="Unique identifier for the candidate")
    name: str = Field(description="Candidate's full name")
    current_title: str = Field(description="Candidate's current job title")
    skills: list[str] = Field(description="List of skills the candidate possesses")
    years_of_experience: int = Field(description="Total years of professional experience")
    summary: str = Field(description="A brief summary or bio of the candidate")
    
    # We will use this string for generating embeddings
    def to_embedding_text(self) -> str:
        return f"{self.current_title}. Skills: {', '.join(self.skills)}. {self.summary}"

class ScoredCandidate(BaseModel):
    candidate_id: str
    semantic_similarity: float = Field(description="Raw vector search score (0.0 to 1.0)")
    llm_rerank_score: float = Field(description="LLM evaluation score (0.0 to 1.0)")
    final_score: float = Field(description="Combined or final score used for sorting")
    matched_skills: list[str] = Field(description="Skills from JD that the candidate has")
    missing_skills: list[str] = Field(description="Skills from JD that the candidate is missing")
    rationale: str = Field(description="Brief explanation of why the candidate received this score")
