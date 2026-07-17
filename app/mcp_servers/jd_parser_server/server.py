import sys
import logging
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# We import the adapter directly here for simplicity, although in a strict microservice 
# architecture this server might have its own copy of the adapter or use HTTP.
from app.llm.provider_adapter import get_llm_provider
from app.schemas.jd import ExtractedJD

# Initialize FastMCP server
mcp = FastMCP("jd-parser-server")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jd-parser-server")

@mcp.tool()
async def parse_raw_jd(raw_text: str) -> str:
    """
    Parses a raw Job Description text and returns a structured JSON string 
    representing the ExtractedJD schema.
    """
    logger.info("Parsing raw JD...")
    
    llm = get_llm_provider()
    
    system_prompt = """
    You are an expert technical recruiter and HR data extractor.
    Your job is to read a raw Job Description and extract structured information exactly matching the schema.
    If you see contradictory information, use your best judgement. 
    Be highly strict about red flags (e.g. 'rockstar', 'ninja', 'work hard play hard', unpaid tasks).
    If experience band is not explicitly stated, infer it from years of experience (0-2: junior, 3-5: mid, 6-9: senior, 10+: staff+).
    """
    
    try:
        extracted = await llm.generate_structured_output(
            prompt=raw_text,
            response_model=ExtractedJD,
            system_prompt=system_prompt
        )
        return extracted.model_dump_json()
    except Exception as e:
        logger.error(f"Error extracting JD: {e}")
        return f"Error: {e}"

class NormalizedSkill(BaseModel):
    normalized_name: str

@mcp.tool()
async def normalize_skill_taxonomy(skill_name: str) -> str:
    """
    Normalizes a skill name to a standard taxonomy using the LLM.
    """
    llm = get_llm_provider()
    system_prompt = "You are an expert technical recruiter. Map the given skill to the standard industry taxonomy name (e.g., 'reactjs' -> 'React', 'golang' -> 'Go', 'nodejs' -> 'Node.js'). Output the standard capitalized name."
    
    try:
        result = await llm.generate_structured_output(
            prompt=skill_name,
            response_model=NormalizedSkill,
            system_prompt=system_prompt
        )
        return result.normalized_name
    except Exception as e:
        logger.error(f"Failed to normalize skill {skill_name}: {e}")
        return skill_name.title()

if __name__ == "__main__":
    # Run the server on stdio
    mcp.run()
