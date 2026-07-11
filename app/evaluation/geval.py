"""
G-Eval scoring implementation.
Uses LLM-as-judge with chain-of-thought reasoning to score agent outputs
on relevance, faithfulness, and completeness.
"""
import logging
from pydantic import BaseModel, Field

from app.llm.provider_adapter import get_llm_provider
from app.schemas.eval import EvalResult
from app.evaluation.thresholds import get_thresholds, compute_overall_confidence

logger = logging.getLogger(__name__)


class GEvalScores(BaseModel):
    """Schema for the LLM judge's structured output."""
    relevance: float = Field(description="How relevant is the output to the task (0.0-1.0)")
    faithfulness: float = Field(description="Is the output faithful to source data, no hallucination (0.0-1.0)")
    completeness: float = Field(description="How complete is the output relative to what was asked (0.0-1.0)")
    reasoning: str = Field(description="Step-by-step chain-of-thought reasoning for the scores")


EVAL_SYSTEM_PROMPT = """
You are an expert evaluator for an AI hiring pipeline. Your job is to evaluate the quality 
of an agent's output given the task definition and input context.

Score each dimension from 0.0 to 1.0:

1. **Relevance** (0.0-1.0): Does the output directly address the task? Are all parts of the 
   output relevant to the input? A score of 1.0 means every piece of information is relevant.

2. **Faithfulness** (0.0-1.0): Is every claim in the output grounded in the input data? 
   Are there any hallucinated facts, invented skills, or fabricated details? 
   A score of 1.0 means zero hallucination.

3. **Completeness** (0.0-1.0): Does the output cover all required aspects of the task? 
   Are any important pieces missing? A score of 1.0 means nothing important was omitted.

Think step by step before providing your scores. Be strict but fair.
"""


async def evaluate_agent_output(
    agent_name: str,
    task_id: str,
    task_description: str,
    input_context: str,
    agent_output: str,
) -> EvalResult:
    """
    Evaluate an agent's output using G-Eval (LLM-as-judge).
    
    Args:
        agent_name: Name of the agent being evaluated.
        task_id: ID of the task.
        task_description: Description of what the task was supposed to do.
        input_context: The input that was given to the agent.
        agent_output: The output the agent produced.
    
    Returns:
        EvalResult with scores and human review flag.
    """
    llm = get_llm_provider()

    prompt = f"""
## Task Definition
{task_description}

## Input Context
{input_context}

## Agent Output to Evaluate
{agent_output}

Evaluate the agent output above against the task definition and input context.
Think step by step, then provide your scores.
"""

    try:
        scores = await llm.generate_structured_output(
            prompt=prompt,
            response_model=GEvalScores,
            system_prompt=EVAL_SYSTEM_PROMPT,
        )

        overall = compute_overall_confidence(
            scores.relevance, scores.faithfulness, scores.completeness
        )

        # Check against thresholds
        thresholds = get_thresholds(agent_name)
        needs_review = False
        review_reasons = []

        if scores.relevance < thresholds.get("relevance", 0.70):
            needs_review = True
            review_reasons.append(f"Relevance {scores.relevance:.2f} < {thresholds['relevance']}")
        if scores.faithfulness < thresholds.get("faithfulness", 0.70):
            needs_review = True
            review_reasons.append(f"Faithfulness {scores.faithfulness:.2f} < {thresholds['faithfulness']}")
        if scores.completeness < thresholds.get("completeness", 0.60):
            needs_review = True
            review_reasons.append(f"Completeness {scores.completeness:.2f} < {thresholds['completeness']}")

        review_reason = "; ".join(review_reasons) if review_reasons else None

        return EvalResult(
            agent=agent_name,
            task_id=task_id,
            relevance=scores.relevance,
            faithfulness=scores.faithfulness,
            completeness=scores.completeness,
            overall_confidence=round(overall, 4),
            needs_human_review=needs_review,
            review_reason=review_reason,
        )

    except Exception as e:
        logger.error(f"G-Eval failed for {agent_name}/{task_id}: {e}")
        # On eval failure, flag for human review (fail safe, never silent pass)
        return EvalResult(
            agent=agent_name,
            task_id=task_id,
            relevance=0.0,
            faithfulness=0.0,
            completeness=0.0,
            overall_confidence=0.0,
            needs_human_review=True,
            review_reason=f"Evaluation failed: {e}",
        )
