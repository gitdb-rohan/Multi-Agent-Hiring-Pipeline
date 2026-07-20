from app.infra.db import ScoredCandidateDB


def test_scored_candidate_db_accepts_detailed_scores():
    candidate = ScoredCandidateDB(
        run_id="run-1",
        candidate_id="candidate-1",
        semantic_similarity=0.72,
        llm_rerank_score=0.88,
        final_score=0.816,
        matched_skills_json=["Python", "FastAPI"],
        missing_skills_json=["Kubernetes"],
        rationale_json="Strong backend fit with a deployment gap.",
    )

    assert candidate.semantic_similarity == 0.72
    assert candidate.llm_rerank_score == 0.88
    assert candidate.matched_skills_json == ["Python", "FastAPI"]
    assert candidate.missing_skills_json == ["Kubernetes"]
