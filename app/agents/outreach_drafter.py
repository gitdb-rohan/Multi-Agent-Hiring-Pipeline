import json
import logging
from typing import List

from pydantic import BaseModel
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from contextlib import AsyncExitStack

from app.agents.base import BaseAgent, with_retry
from app.llm.provider_adapter import get_llm_provider
from app.schemas.outreach import OutreachEmail
from app.schemas.candidate import ScoredCandidate
from app.schemas.jd import ExtractedJD
from app.infra.vector_store import vector_store

logger = logging.getLogger(__name__)

class OutreachDrafterRequest(BaseModel):
    jd: ExtractedJD
    scored_candidates: List[ScoredCandidate]

class OutreachDrafterResponse(BaseModel):
    emails: List[OutreachEmail]
    send_results: list = []

    TASK_DESCRIPTION = "Draft personalized, professional outreach emails for shortlisted candidates"

    def __init__(self):
        super().__init__(name="OutreachDrafter")
        self.llm = get_llm_provider()

    def build_request(self, context: dict) -> OutreachDrafterRequest:
        jd_data = context.get("extracted_jd")
        if isinstance(jd_data, dict):
            jd = ExtractedJD(**jd_data)
        else:
            jd = jd_data
        
        candidates_data = context.get("scored_candidates", [])
        candidates = []
        for c in candidates_data:
            if isinstance(c, dict):
                candidates.append(ScoredCandidate(**c))
            else:
                candidates.append(c)
        
        return OutreachDrafterRequest(jd=jd, scored_candidates=candidates)

    def store_result(self, result: OutreachDrafterResponse, context: dict) -> None:
        context["outreach_emails"] = [e.model_dump() for e in result.emails]
        context["send_results"] = result.send_results

    def get_summary(self, result: OutreachDrafterResponse) -> str:
        return f"Drafted {len(result.emails)} outreach emails"

    def get_eval_input_context(self, context: dict) -> str:
        return json.dumps({
            "jd": context.get("extracted_jd", {}),
            "candidates": context.get("scored_candidates", [])[:3],
        }, default=str)

    def parse_cached_result(self, output_json: dict) -> OutreachDrafterResponse:
        return OutreachDrafterResponse(**output_json)

    @with_retry(max_retries=3, base_delay=2.0)
    async def _execute(self, request: OutreachDrafterRequest) -> OutreachDrafterResponse:
        logger.info(f"{self.name} drafting emails for {len(request.scored_candidates)} candidates...")
        
        is_manual = "Intent:" in request.jd.role_title
        cand_name = self.context.get('cand_name', 'Candidate')
        
        intent_query = request.jd.role_title if is_manual else "reach out to candidate"
        templates = vector_store.search_templates(intent_query, top_k=2)
        template_text = "\n---\n".join(templates) if templates else "None available."

        system_prompt = f"""
You are a professional technical recruiter writing personalized cold outreach emails.
Role context / Instructions: {request.jd.role_title}

IMPORTANT: The system will automatically wrap your generated body in a standard company HTML header and footer.
You must ONLY generate the body text. Do not include signatures like "Best, HR Team" or headers like "Subject:".
Output only the raw text/HTML body.

Here are some standard company email templates you should try to follow for tone and structure:
{template_text}
"""

        import asyncio
        
        async def _draft_single_email(candidate: ScoredCandidate) -> OutreachEmail | None:
            prompt = f"""
Candidate ID: {candidate.candidate_id}
Candidate Name: {cand_name}
Matched Skills: {', '.join(candidate.matched_skills)}
Missing Skills: {', '.join(candidate.missing_skills)}
Score Rationale: {candidate.rationale}
Final Score: {candidate.final_score}

Draft the subject line and the body of the personalized outreach email for {cand_name}.
"""
            try:
                email = await self.llm.generate_structured_output(
                    prompt=prompt,
                    response_model=OutreachEmail,
                    system_prompt=system_prompt,
                )
                email.candidate_id = candidate.candidate_id
                return email
            except Exception as e:
                logger.error(f"Failed to draft email for {candidate.candidate_id}: {e}")
                return None

        # Execute all LLM drafting calls concurrently
        tasks = [_draft_single_email(c) for c in request.scored_candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        emails: List[OutreachEmail] = []
        for r in results:
            if isinstance(r, OutreachEmail):
                emails.append(r)
            elif isinstance(r, Exception):
                logger.error(f"Concurrency error during email drafting: {r}")

        logger.info(f"OutreachDrafter completed: {len(emails)} emails drafted.")
        return OutreachDrafterResponse(emails=emails, send_results=[])
