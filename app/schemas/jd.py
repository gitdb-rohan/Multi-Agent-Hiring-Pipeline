from typing import Literal
from pydantic import BaseModel, Field

class RedFlag(BaseModel):
    flag: str = Field(description="The actual red flag identified in the text")
    severity: Literal["low", "medium", "high"] = Field(description="Severity of the red flag")
    evidence_snippet: str = Field(description="The exact snippet from the JD that indicates this red flag")

class ExtractedJD(BaseModel):
    role_title: str = Field(description="The exact or inferred title of the role")
    required_skills: list[str] = Field(description="List of explicitly required skills")
    nice_to_have_skills: list[str] = Field(description="List of bonus or nice-to-have skills")
    experience_band: Literal["junior", "mid", "senior", "staff+"] = Field(description="The seniority level expected")
    min_years_experience: int = Field(description="Minimum years of experience required (0 if none specified)")
    red_flags: list[RedFlag] = Field(description="Any red flags or warning signs in the JD")
    confidence: float = Field(description="Self-reported confidence in the extraction (0.0 to 1.0)")
