from pydantic import BaseModel, Field

class OutreachEmail(BaseModel):
    candidate_id: str = Field(description="The ID of the candidate this email is for")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Full email body text")
    personalization_points: list[str] = Field(description="Specific points used to personalize this email")
