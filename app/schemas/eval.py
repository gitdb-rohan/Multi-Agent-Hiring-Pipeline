from pydantic import BaseModel, Field

class EvalResult(BaseModel):
    agent: str = Field(description="Name of the agent that produced the output")
    task_id: str = Field(description="ID of the task that was evaluated")
    relevance: float = Field(description="How relevant the output is to the input (0.0-1.0)")
    faithfulness: float = Field(description="How faithful the output is to the source data, no hallucination (0.0-1.0)")
    completeness: float = Field(description="How complete the output is relative to what was asked (0.0-1.0)")
    overall_confidence: float = Field(description="Weighted overall confidence score (0.0-1.0)")
    needs_human_review: bool = Field(description="Whether this output was flagged for human review")
    review_reason: str | None = Field(default=None, description="Reason for flagging, if applicable")
