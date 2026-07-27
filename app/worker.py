import asyncio
from app.infra.db import get_db_session, Run, PipelineContext, TaskState
from sqlalchemy.future import select
import logging

logger = logging.getLogger(__name__)

async def run_pipeline_in_background(run_id: str, extra_k: int = 0):
    with open("/tmp/worker_debug.txt", "a") as f: f.write(f"worker started for {run_id}\n")
    try:
        from app.orchestration.state_machine import PipelineStateMachine
        from app.orchestration.task_graph import TaskGraph, Task
        from app.agents.jd_analyser import JDAnalyser
        from app.agents.candidate_scorer import CandidateScorer
        from app.agents.outreach_drafter import OutreachDrafter
        
        async for db in get_db_session():
            db_run = await db.get(Run, run_id)
            if not db_run:
                logger.error(f"Run {run_id} not found")
                return
                
            if db_run.status in ["completed", "failed"] and extra_k == 0:
                return

            # Fetch context
            context_result = await db.execute(select(PipelineContext).where(PipelineContext.run_id == run_id))
            context_obj = context_result.scalars().first()
            import copy
            context = copy.deepcopy(context_obj.context_data) if context_obj and context_obj.context_data else {}

            if extra_k > 0:
                context["top_k"] = context.get("top_k", 5) + extra_k

            # Build TaskGraph directly (Planner agent is unnecessary)
            task_graph = TaskGraph(run_id=run_id)
            task_graph.tasks = [
                Task(name="extract_jd", agent="JDAnalyser", depends_on=[]),
                Task(name="score_candidates", agent="CandidateScorer", depends_on=["extract_jd"]),
                Task(name="draft_outreach", agent="OutreachDrafter", depends_on=["score_candidates"]),
            ]
            
            # Hydrate task status from db
            task_states = await db.execute(select(TaskState).where(TaskState.run_id == run_id))
            completed_agents = {t.agent_name for t in task_states.scalars() if t.status == "COMPLETED"}
            
            for task in task_graph.tasks:
                if task.agent in completed_agents:
                    # If we are continuing with extra_k, we want to re-run CandidateScorer and OutreachDrafter,
                    # but we can skip JDAnalyser since the JD hasn't changed.
                    if extra_k > 0 and task.agent in ["CandidateScorer", "OutreachDrafter"]:
                        continue
                    task.status = "completed"

            machine = PipelineStateMachine(task_graph, context)
            
            # Restore state
            if db_run.status == "paused_for_review":
                machine.state = "paused_for_review"
            elif db_run.status == "needs_review":
                machine.state = "needs_review"

            try:
                result = await machine.run(db=db)
                with open("/tmp/worker_debug.txt", "a") as f: f.write(f"machine.run finished with result {result}\n")
            except Exception as inner_e:
                with open("/tmp/worker_debug.txt", "a") as f: f.write(f"machine.run raised {inner_e}\n")
                raise inner_e

            # Save context
            if not context_obj:
                context_obj = PipelineContext(run_id=run_id, context_data=machine.context)
                db.add(context_obj)
            else:
                from sqlalchemy.orm.attributes import flag_modified
                context_obj.context_data = machine.context
                flag_modified(context_obj, "context_data")
                db.add(context_obj)

            db_run.status = result.get("status", "failed")
            await db.commit()
            with open("/tmp/worker_debug.txt", "a") as f: f.write(f"committed db_run.status={db_run.status}\n")
    except Exception as e:
        logger.exception(f"Fatal error in pipeline {run_id}")
        from app.orchestration.events import event_emitter, PipelineEvent
        
        # Broadcast error to UI
        await event_emitter.emit(PipelineEvent(
            run_id=run_id,
            event_type="error",
            data={"error": f"Fatal worker error: {str(e)}"}
        ))
        
        # Update DB
        try:
            async for db in get_db_session():
                db_run = await db.get(Run, run_id)
                if db_run:
                    db_run.status = "failed"
                    await db.commit()
                break
        except Exception:
            pass
