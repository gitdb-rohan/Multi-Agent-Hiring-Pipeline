"""
LLM-powered profile extraction from raw resume text.
Takes unstructured resume text and produces a structured CandidateProfile
using the configured LLM provider.
"""
import logging
from app.llm.provider_adapter import get_llm_provider
from app.schemas.candidate import CandidateProfile, generate_candidate_id

logger = logging.getLogger(__name__)


RESUME_EXTRACTION_PROMPT = """
You are an expert HR data extraction system. Given a candidate's resume text,
extract a structured profile with the following fields:

- **name**: The candidate's full name.
- **email**: The candidate's email address. If not found, return empty string.
- **current_title**: Their most recent or current job title.
- **skills**: A comprehensive list of technical and professional skills mentioned.
- **years_of_experience**: Total years of professional experience (estimate from work history dates; 0 if unclear).
- **previous_companies**: List of companies they've worked at (most recent first).
- **projects**: List of notable projects, achievements, or open-source contributions mentioned.
- **position_applied**: Leave as empty string (will be set by the system).
- **summary**: A concise 2-3 sentence professional summary synthesized from the resume.

Rules:
- Extract ONLY what is explicitly stated in the resume. Do NOT invent or hallucinate details.
- For skills, include both explicitly listed skills and skills clearly implied by work experience.
- For years_of_experience, calculate from the earliest employment date to present if dates are given.
- If the email is missing, return an empty string — do NOT invent one.
- Set id to an empty string — the system will generate it from the email.
"""


async def extract_profile_from_resume(
    raw_text: str,
    position_applied: str = "",
) -> CandidateProfile:
    """
    Use the LLM to extract a structured CandidateProfile from raw resume text.
    
    Args:
        raw_text: The raw text extracted from a resume file.
        position_applied: Optional position the candidate is applying for.
        
    Returns:
        A populated CandidateProfile with a deterministic ID derived from the email.
        
    Raises:
        ValueError: If no email could be extracted (needed for dedup).
    """
    llm = get_llm_provider()
    
    logger.info("Extracting candidate profile from resume text via LLM...")
    
    profile = await llm.generate_structured_output(
        prompt=f"Extract the candidate profile from this resume:\n\n{raw_text}",
        response_model=CandidateProfile,
        system_prompt=RESUME_EXTRACTION_PROMPT,
    )
    
    # Override position_applied if provided by the system
    if position_applied:
        profile.position_applied = position_applied
    
    # Generate deterministic ID from email for dedup
    if profile.email:
        profile.id = generate_candidate_id(profile.email)
        logger.info(f"Extracted profile for {profile.name} ({profile.email}) → ID: {profile.id}")
    else:
        # Fallback: hash name if no email found (less reliable dedup)
        import hashlib
        fallback_key = profile.name.lower().strip()
        profile.id = f"cand_{hashlib.md5(fallback_key.encode()).hexdigest()[:12]}"
        logger.warning(
            f"No email found for {profile.name} — using name-based fallback ID: {profile.id}. "
            "Dedup may be unreliable without an email."
        )
    
    return profile
