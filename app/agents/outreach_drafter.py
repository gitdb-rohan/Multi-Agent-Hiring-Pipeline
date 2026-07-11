import json
import logging
from typing import List
from pydantic import BaseModel
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agents.base import BaseAgent, with_retry
from app.schemas.jd import ExtractedJD
from app.schemas.candidate import ScoredCandidate
from app.schemas.outreach import OutreachEmail
from app.llm.provider_adapter import get_llm_provider

logger = logging.getLogger(__name__)


class OutreachDrafterRequest(BaseModel):
    jd: ExtractedJD
    scored_candidates: List[ScoredCandidate]


class OutreachDrafterResponse(BaseModel):
    emails: List[OutreachEmail]
    send_results: List[dict]


class OutreachDrafter(BaseAgent):
    """
    Agent responsible for drafting personalized outreach emails for shortlisted candidates,
    then sending them via the email-server MCP (rate-limited).
    """

    def __init__(self):
        super().__init__(name="OutreachDrafter")
        self.server_params = StdioServerParameters(
            command="uv",
            args=["run", "python", "-m", "app.mcp_servers.email_server.server"],
            env=None,
        )
        self.llm = get_llm_provider()

    @with_retry(max_retries=3, base_delay=2.0)
    async def _execute(self, request: OutreachDrafterRequest) -> OutreachDrafterResponse:
        logger.info(f"{self.name} drafting emails for {len(request.scored_candidates)} candidates...")

        # 1. Draft emails using LLM
        system_prompt = f"""
You are a professional technical recruiter writing personalized cold outreach emails.
Role: {request.jd.role_title}
Required Skills: {', '.join(request.jd.required_skills)}

Write a warm, professional, concise email (under 200 words) that:
- References the candidate's specific skills and experience
- Explains why they'd be a great fit for this specific role
- Has a clear call to action
- Feels human, not templated

Do NOT use generic filler. Every sentence must reference something specific about the candidate.
"""

        emails: List[OutreachEmail] = []
        for candidate in request.scored_candidates:
            prompt = f"""
Candidate ID: {candidate.candidate_id}
Matched Skills: {', '.join(candidate.matched_skills)}
Missing Skills: {', '.join(candidate.missing_skills)}
Score Rationale: {candidate.rationale}
Final Score: {candidate.final_score}

Draft a personalized outreach email for this candidate.
"""
            try:
                email = await self.llm.generate_structured_output(
                    prompt=prompt,
                    response_model=OutreachEmail,
                    system_prompt=system_prompt,
                )
                # Override the candidate_id to ensure consistency
                email.candidate_id = candidate.candidate_id
                emails.append(email)
            except Exception as e:
                logger.error(f"Failed to draft email for {candidate.candidate_id}: {e}")

        # 2. Send emails via MCP (rate-limited)
        send_results = []
        async with AsyncExitStack() as stack:
            read, write = await stack.enter_async_context(stdio_client(self.server_params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            for email in emails:
                try:
                    result = await session.call_tool(
                        name="send_outreach_email",
                        arguments={
                            "candidate_id": email.candidate_id,
                            "subject": email.subject,
                            "body": email.body,
                        },
                    )
                    if result.isError:
                        send_results.append({"candidate_id": email.candidate_id, "status": "error", "detail": str(result.content)})
                    else:
                        send_results.append(json.loads(result.content[0].text))
                except Exception as e:
                    send_results.append({"candidate_id": email.candidate_id, "status": "error", "detail": str(e)})

        logger.info(f"{self.name} completed: {len(emails)} emails drafted, {len(send_results)} send attempts.")
        return OutreachDrafterResponse(emails=emails, send_results=send_results)
