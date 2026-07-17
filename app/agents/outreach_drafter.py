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

class OutreachDrafter(BaseAgent):
    def __init__(self):
        super().__init__(name="OutreachDrafter")
        self.llm = get_llm_provider()

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

        emails: List[OutreachEmail] = []
        for candidate in request.scored_candidates:
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
                emails.append(email)
            except Exception as e:
                logger.error(f"Failed to draft email for {candidate.candidate_id}: {e}")

        logger.info(f"OutreachDrafter completed: {len(emails)} emails drafted.")
        return OutreachDrafterResponse(emails=emails, send_results=[])
