import pytest
from app.schemas.candidate import CandidateProfile, ScoredCandidate

def test_candidate_profile_embedding_text():
    c = CandidateProfile(
        id="123",
        name="Test",
        current_title="Dev",
        skills=["A", "B"],
        years_of_experience=2,
        summary="A summary."
    )
    
    text = c.to_embedding_text()
    assert "Dev" in text
    assert "A, B" in text
    assert "summary" in text

def test_scored_candidate_validation():
    data = {
        "candidate_id": "123",
        "semantic_similarity": 0.8,
        "llm_rerank_score": 0.9,
        "final_score": 0.86,
        "matched_skills": ["A"],
        "missing_skills": ["B"],
        "rationale": "Good fit."
    }
    
    sc = ScoredCandidate(**data)
    assert sc.final_score == 0.86
    assert len(sc.matched_skills) == 1
