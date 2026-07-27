import json
import logging
import sys
from typing import List
from pydantic import BaseModel
from contextlib import AsyncExitStack

# Using the official mcp sdk client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agents.base import BaseAgent, with_retry
from app.schemas.jd import ExtractedJD
from app.schemas.candidate import ScoredCandidate
from app.llm.provider_adapter import get_llm_provider

logger = logging.getLogger(__name__)

class CandidateScorerRequest(BaseModel):
    jd: ExtractedJD
    top_k: int = 5

class CandidateScorerResponse(BaseModel):
    scored_candidates: List[ScoredCandidate]

class CandidateScorer(BaseAgent):
    """
    Agent responsible for scoring candidates against a job description.
    
    Search architecture (recall + precision, no keyword index):
    
    1. **Vector similarity for recall**: Queries ChromaDB with a semantic search string
       built from the JD (role title + required skills + nice-to-haves). ChromaDB uses
       cosine similarity (derived from L2 distance) with all-MiniLM-L6-v2 embeddings
       to return the top-K most semantically similar candidates. This casts a wide net.
    
    2. **LLM re-ranker for precision**: Each candidate is then evaluated by the LLM with
       a structured output schema that explicitly extracts `matched_skills` and `missing_skills`
       against the JD requirements. This acts as the exact-skill check without needing a 
       separate BM25/keyword index — the LLM is effectively performing keyword-level matching
       as part of its re-ranking.
    
    3. **Final score**: 40% semantic similarity + 60% LLM re-rank score. The heavier LLM
       weight ensures that keyword-level skill matching dominates over pure embedding distance.
    """
    TASK_DESCRIPTION = "Score and rank candidates against extracted job requirements using vector similarity and LLM re-ranking"

    def __init__(self):
        super().__init__(name="CandidateScorer")
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_servers.candidate_db_server.server"],
            env=None
        )
        self.llm = get_llm_provider()

    def build_request(self, context: dict) -> CandidateScorerRequest:
        jd_data = context.get("extracted_jd")
        if isinstance(jd_data, dict):
            jd = ExtractedJD(**jd_data)
        else:
            jd = jd_data
        return CandidateScorerRequest(jd=jd, top_k=context.get("top_k", 5))

    def store_result(self, result: CandidateScorerResponse, context: dict) -> None:
        context["scored_candidates"] = [c.model_dump() for c in result.scored_candidates]

    def get_summary(self, result: CandidateScorerResponse) -> str:
        return f"Scored {len(result.scored_candidates)} candidates"

    def get_eval_input_context(self, context: dict) -> str:
        return json.dumps(context.get("extracted_jd", {}), default=str)

    def parse_cached_result(self, output_json: dict) -> CandidateScorerResponse:
        return CandidateScorerResponse(**output_json)

    @with_retry(max_retries=3, base_delay=2.0)
    async def _execute(self, request: CandidateScorerRequest) -> CandidateScorerResponse:
        logger.info(f"{self.name} starting scoring process...")
        
        # 1. Generate search query from JD
        search_query = f"{request.jd.role_title}. Required: {', '.join(request.jd.required_skills)}. Nice to have: {', '.join(request.jd.nice_to_have_skills)}"
        
        # 2. Vector search via MCP
        async with AsyncExitStack() as stack:
            read, write = await stack.enter_async_context(stdio_client(self.server_params))
            session = await stack.enter_async_context(ClientSession(read, write))
            
            await session.initialize()
            
            logger.info(f"Calling vector_search_candidates with query: {search_query}")
            search_result = await session.call_tool(
                name="vector_search_candidates",
                arguments={"query": search_query, "top_k": request.top_k}
            )
            
            if search_result.isError:
                raise RuntimeError(f"MCP Tool Error: {search_result.content}")
                
            raw_candidates_str = search_result.content[0].text
            raw_candidates = json.loads(raw_candidates_str)
            
            if "error" in raw_candidates:
                raise RuntimeError(f"Vector search failed: {raw_candidates['error']}")

        # 3. LLM Re-ranking & Scoring
        logger.info(f"LLM re-ranking {len(raw_candidates)} candidates...")
        
        system_prompt = f"""
        You are an expert technical recruiter scoring candidates against a job description.
        Job Title: {request.jd.role_title}
        Required Skills: {', '.join(request.jd.required_skills)}
        Experience Level: {request.jd.experience_band} (min {request.jd.min_years_experience} yrs)
        
        Given the candidate profile, score them from 0.0 to 1.0 based on how well they fit.
        Be strict about explicitly required skills.
        Provide a concise rationale.
        """

        class LLMScoringResult(BaseModel):
            llm_rerank_score: float
            matched_skills: List[str]
            missing_skills: List[str]
            rationale: str

        import asyncio

        async def _score_single_candidate(candidate_data: dict) -> ScoredCandidate | None:
            candidate_id = candidate_data.get("id")
            candidate_doc = candidate_data.get("document", "")
            semantic_score = candidate_data.get("similarity_score", 0.0)
            
            prompt = f"Candidate Profile:\n{candidate_doc}\nEvaluate this candidate."
            
            try:
                llm_eval = await self.llm.generate_structured_output(
                    prompt=prompt,
                    response_model=LLMScoringResult,
                    system_prompt=system_prompt
                )
                
                final_score = (semantic_score * 0.4) + (llm_eval.llm_rerank_score * 0.6)
                
                return ScoredCandidate(
                    candidate_id=candidate_id,
                    semantic_similarity=semantic_score,
                    llm_rerank_score=llm_eval.llm_rerank_score,
                    final_score=round(final_score, 4),
                    matched_skills=llm_eval.matched_skills,
                    missing_skills=llm_eval.missing_skills,
                    rationale=llm_eval.rationale
                )
            except Exception as e:
                logger.error(f"Failed to score candidate {candidate_id}: {e}")
                return None

        # Execute all LLM calls concurrently
        tasks = [_score_single_candidate(c) for c in raw_candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out errors and None values
        scored_candidates = []
        for r in results:
            if isinstance(r, ScoredCandidate):
                scored_candidates.append(r)
            elif isinstance(r, Exception):
                logger.error(f"Concurrency error during candidate scoring: {r}")
                
        # Sort by final score descending
        scored_candidates.sort(key=lambda x: x.final_score, reverse=True)
        
        return CandidateScorerResponse(scored_candidates=scored_candidates)
