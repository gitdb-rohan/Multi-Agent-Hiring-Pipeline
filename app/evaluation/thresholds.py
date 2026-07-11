"""
Confidence thresholds per agent type.
If an agent's output scores below these thresholds on any dimension, it is flagged for human review.
"""


# Per-agent thresholds: {dimension: minimum_score}
AGENT_THRESHOLDS: dict[str, dict[str, float]] = {
    "JDAnalyser": {
        "relevance": 0.75,
        "faithfulness": 0.80,  # Stricter: JD extraction must not hallucinate
        "completeness": 0.70,
    },
    "CandidateScorer": {
        "relevance": 0.70,
        "faithfulness": 0.75,
        "completeness": 0.65,
    },
    "OutreachDrafter": {
        "relevance": 0.70,
        "faithfulness": 0.75,
        "completeness": 0.60,
    },
}

# Overall confidence threshold (weighted average)
DEFAULT_OVERALL_THRESHOLD = 0.75

# Weights for computing overall confidence
DIMENSION_WEIGHTS = {
    "relevance": 0.35,
    "faithfulness": 0.40,
    "completeness": 0.25,
}


def get_thresholds(agent_name: str) -> dict[str, float]:
    """Get the thresholds for a given agent. Falls back to defaults."""
    return AGENT_THRESHOLDS.get(agent_name, {
        "relevance": 0.70,
        "faithfulness": 0.70,
        "completeness": 0.60,
    })


def compute_overall_confidence(relevance: float, faithfulness: float, completeness: float) -> float:
    """Compute weighted overall confidence score."""
    return (
        relevance * DIMENSION_WEIGHTS["relevance"]
        + faithfulness * DIMENSION_WEIGHTS["faithfulness"]
        + completeness * DIMENSION_WEIGHTS["completeness"]
    )
