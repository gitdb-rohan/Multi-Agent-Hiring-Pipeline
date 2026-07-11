"""
Planner Agent — decomposes a hiring goal into an ordered TaskGraph and dispatches execution.
The Planner never talks to MCP servers directly; it only knows task graphs and agent contracts.
"""
import logging
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, with_retry
from app.orchestration.task_graph import TaskGraph, Task
from app.orchestration.state_machine import PipelineStateMachine

logger = logging.getLogger(__name__)


class PlannerRequest(BaseModel):
    run_id: str = Field(description="The unique identifier for this pipeline run")
    goal_text: str = Field(description="The recruiter's hiring goal in plain English")
    raw_jd_text: str = Field(description="The raw job description text")
    top_k: int = Field(default=5, description="Number of top candidates to shortlist")


class PlannerResponse(BaseModel):
    run_id: str
    status: str
    context: dict
    eval_results: list = Field(default_factory=list)
    graph_summary: dict = Field(default_factory=dict)


class PlannerAgent(BaseAgent):
    """
    Supervisor agent that:
    1. Decomposes a hiring goal into an ordered task graph.
    2. Dispatches the graph to the state machine for execution.
    """

    def __init__(self):
        super().__init__(name="PlannerAgent")

    def _build_task_graph(self, request: PlannerRequest) -> TaskGraph:
        """
        Build the standard hiring pipeline task graph:
          extract_jd → score_candidates → draft_outreach
        """
        graph = TaskGraph(run_id=request.run_id)

        graph.tasks = [
            Task(
                name="extract_jd",
                agent="JDAnalyser",
                depends_on=[],
            ),
            Task(
                name="score_candidates",
                agent="CandidateScorer",
                depends_on=["extract_jd"],
            ),
            Task(
                name="draft_outreach",
                agent="OutreachDrafter",
                depends_on=["score_candidates"],
            ),
        ]

        return graph

    @with_retry(max_retries=2, base_delay=1.0)
    async def _execute(self, request: PlannerRequest) -> PlannerResponse:
        logger.info(f"{self.name} building task graph for goal: {request.goal_text[:80]}...")

        # 1. Build the task graph
        task_graph = self._build_task_graph(request)
        logger.info(f"Task graph built: {task_graph.summary()}")

        # 2. Create state machine and seed context
        sm = PipelineStateMachine(task_graph)
        sm.context["raw_jd_text"] = request.raw_jd_text
        sm.context["goal_text"] = request.goal_text
        sm.context["top_k"] = request.top_k

        # 3. Run the pipeline
        result = await sm.run()

        return PlannerResponse(
            run_id=task_graph.run_id,
            status=result.get("status", "unknown"),
            context=result.get("context", {}),
            eval_results=result.get("eval_results", []),
            graph_summary=result.get("graph_summary", {}),
        )
