import asyncio
import logging
from app.agents.candidate_scorer import CandidateScorer, CandidateScorerRequest
from app.schemas.jd import ExtractedJD

logging.basicConfig(level=logging.INFO)

async def main():
    # Mock an ExtractedJD that would have come from the JDAnalyser
    jd = ExtractedJD(
        role_title="Senior Backend Engineer",
        required_skills=["Python", "FastAPI", "PostgreSQL"],
        nice_to_have_skills=["Docker", "AWS"],
        experience_band="senior",
        min_years_experience=4,
        red_flags=[],
        confidence=0.95
    )
    
    agent = CandidateScorer()
    request = CandidateScorerRequest(jd=jd, top_k=3)
    
    try:
        result = await agent.run(request)
        print("\n--- SCORING RESULT ---")
        for sc in result.scored_candidates:
            print(f"\nCandidate ID: {sc.candidate_id}")
            print(f"Final Score: {sc.final_score}")
            print(f"Semantic: {sc.semantic_similarity}, LLM: {sc.llm_rerank_score}")
            print(f"Matched Skills: {sc.matched_skills}")
            print(f"Missing Skills: {sc.missing_skills}")
            print(f"Rationale: {sc.rationale}")
        print("\n----------------------\n")
    except Exception as e:
        print(f"Scoring failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
