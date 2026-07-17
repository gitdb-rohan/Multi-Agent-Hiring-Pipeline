# Multi-Agent Business Process Automation — End-to-End Hiring Pipeline

> Supervisor–worker multi-agent system that takes a hiring goal in plain English and produces a scored, vetted, outreach-ready shortlist — with an automated evaluation layer watching every agent's output before it reaches a human.

This document is the **single source of truth** for the project: architecture, tech decisions, folder layout, data contracts, build phases, and setup. Keep it updated as the source of context across sessions.

---

## 1. Decisions Locked In

| Decision | Choice | Reason |
|---|---|---|
| Orchestration | **Custom orchestration** (no LangGraph) | Full control over state machine, retries, and human-in-the-loop hooks; no framework lock-in |
| Tool access | **MCP (Model Context Protocol) servers** | Standard, reusable, swappable tool layer; each tool (JD parsing, candidate DB, email sender) is its own MCP server |
| Frontend feedback | **Streaming (SSE)** | Real-time "Planner → JD Analyser → Scorer → Outreach" progress feed, premium UX instead of spinner-then-dump |
| LLM Provider | **Provider-agnostic** | Swap Anthropic / OpenAI / others via config + adapter layer, no vendor lock-in |
| Structured outputs | **Pydantic v2** everywhere agents hand off data | Enforceable contracts between agents, no fragile string-parsing |
| Vector search | **ChromaDB** | Local-first, easy to self-host, good enough for candidate-profile scale |
| Async/rate-limit | **Redis** (queue + token bucket) | Prevents LLM API throttling, decouples request accept from processing |
| Persistence | **PostgreSQL** | Durable storage of JDs, candidates, scores, outreach emails, eval results |
| API layer | **FastAPI** (async) | Native async, SSE support, Pydantic-native |
| Evaluation | **G-Eval (LLM-as-judge)** methodology, custom implementation | Automatic relevance/faithfulness/completeness scoring, gate on low confidence |
| Observability | **OpenTelemetry** tracing across every agent call | Multi-agent failures are hard to debug without per-step traces |

---

## 2. Plain-English System Overview

1. **Candidate Ingestion** — Resumes (PDF/DOCX) are uploaded via API, batch-imported from a folder, or continuously watched via a directory watcher. Each resume is parsed → LLM-extracted into a structured `CandidateProfile` → deduplicated by email → upserted into ChromaDB.
1b. **Authentication** — HR must register and log in to an account secured via Postgres hashing and tokens before accessing the system.
2. A user (recruiter) submits a **hiring goal** + a **raw job description**.
3. The **Planner Agent** builds a deterministic task graph (`extract_jd → score_candidates → draft_outreach`) and dispatches it through the state machine.
4. **JD Analyser** extracts structured requirements (skills, experience band, red flags) from the raw JD.
5. **Candidate Scorer** uses **vector similarity** (ChromaDB, cosine similarity from L2 distance) for broad recall, then an **LLM re-ranker** for precision — the LLM explicitly extracts `matched_skills` vs. `missing_skills` against JD requirements, which acts as the exact-skill check without needing a separate keyword index. Final score = 40% semantic + 60% LLM re-rank.
6. **Outreach Drafter** writes a personalized cold email per shortlisted candidate. Includes a **RAG component** to search ChromaDB for approved company email templates to ensure brand consistency. HR can also use the **Manual Outreach** tab to draft one-off emails using candidate emails directly, which will be automatically wrapped in standard HTML headers/footers. Includes a **RAG component** to search ChromaDB for approved company email templates to ensure brand consistency. HR can also use the **Manual Outreach** tab to draft one-off emails using candidate emails directly, which will be automatically wrapped in standard HTML headers/footers.
7. The **Evaluation Layer (G-Eval)** runs after each agent, scoring every output on relevance, faithfulness, and completeness. Anything below the agent's threshold is flagged for **human review** — nothing low-confidence leaves the system unreviewed.
8. Everything streams live to the frontend over SSE; final artifacts (JDs, scored candidates, emails, eval results) are persisted to Postgres; emails are rate-limited through Redis.
9. **Audit & Review** — All approved emails, rejections, and manual drafts are tracked in an `Audit Log` tab for accountability. The frontend features a full **Apple-style Liquid Glass Dark Mode UI**.
9. **Audit & Review** — All approved emails, rejections, and manual drafts are tracked in an  tab for accountability. The frontend features a full **Apple-style Liquid Glass Dark Mode UI**.

---

## 3. High-Level Architecture

```mermaid
flowchart TB
    U["Recruiter / API caller"] -->|"POST /pipeline/run"| API["FastAPI Gateway (async)"]
    API --> Q["Redis Queue + Rate Limiter"]
    Q --> PLN["Planner Agent"]

    PLN -->|"task: extract_jd"| JDA["JD Analyser Agent"]
    PLN -->|"task: score_candidates"| CSA["Candidate Scorer Agent"]
    PLN -->|"task: draft_outreach"| ODA["Outreach Drafter Agent"]

    JDA -->|"MCP call"| MCP1["MCP: jd-parser-server"]
    CSA -->|"MCP call"| MCP2["MCP: candidate-db-server (ChromaDB)"]
    ODA -->|"MCP call"| MCP3["MCP: email-server"]

    JDA --> EVAL["Evaluation Layer (G-Eval)"]
    CSA --> EVAL
    ODA --> EVAL

    EVAL -->|"score >= threshold"| DB[("PostgreSQL")]
    EVAL -->|"score < threshold"| HR["Human Review Queue"]
    HR --> DB

    DB --> API
    API -->|"SSE stream"| U
```

**Flow contract:** Planner never talks to MCP servers directly — only sub-agents do. Planner only knows task graphs and agent contracts (Pydantic schemas), keeping it swappable and testable in isolation.

---

## 4. Repository Structure

```
hiring-pipeline/
├── README.md                          <- this file
├── pyproject.toml
├── .env.example
├── docker-compose.yml                 <- postgres, redis, chromadb, api
│
├── app/
│   ├── main.py                        <- FastAPI entrypoint
│   ├── config.py                      <- provider-agnostic LLM config, env settings
│   ├── dependencies.py
│   │
│   ├── agents/
│   │   ├── base.py                    <- BaseAgent class (retry, tracing, logging hooks)
│   │   ├── planner.py                 <- Planner Agent (task decomposition + dispatch)
│   │   ├── jd_analyser.py
│   │   ├── candidate_scorer.py
│   │   └── outreach_drafter.py
│   │
│   ├── orchestration/
│   │   ├── state_machine.py           <- custom orchestration engine
│   │   ├── task_graph.py              <- task/dependency graph model
│   │   └── events.py                  <- SSE event schema + emitter
│   │
│   ├── mcp_servers/
│   │   ├── jd_parser_server/          <- standalone MCP server
│   │   ├── candidate_db_server/       <- wraps ChromaDB as MCP tools
│   │   └── email_server/              <- wraps SMTP/provider as MCP tools
│   │
│   ├── llm/
│   │   ├── provider_adapter.py        <- unifies Anthropic/OpenAI/etc behind one interface
│   │   └── prompts/                   <- versioned prompt templates per agent
│   │
│   ├── schemas/
│   │   ├── jd.py                      <- Pydantic: ExtractedJD, RedFlag, ExperienceBand
│   │   ├── candidate.py                <- Pydantic: CandidateProfile, ScoredCandidate
│   │   ├── outreach.py                 <- Pydantic: OutreachEmail
│   │   └── eval.py                     <- Pydantic: EvalResult (relevance, faithfulness, completeness)
│   │
│   ├── evaluation/
│   │   ├── geval.py                    <- G-Eval scoring implementation
│   │   └── thresholds.py               <- confidence thresholds per agent type
│   │
│   ├── infra/
│   │   ├── db.py                       <- Postgres models (SQLAlchemy async)
│   │   ├── redis_client.py             <- rate limiter + task queue
│   │   ├── vector_store.py             <- ChromaDB client wrapper
│   │   └── tracing.py                  <- OpenTelemetry setup
│   │
│   └── api/
│       ├── routes_pipeline.py          <- POST /pipeline/run, GET /pipeline/{id}/stream (SSE)
│       └── routes_review.py            <- human review queue endpoints
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── eval/                          <- eval-layer regression tests (golden JD set)
│
└── scripts/
    ├── seed_candidates.py             <- load sample candidate pool into ChromaDB
    └── run_eval_report.py             <- batch eval report over past runs
```

---

## 5. Agent Contracts (Pydantic Schemas)

Each agent communicates via a strict schema — never free text. Sketch (final code in `app/schemas/`):

```python
# schemas/jd.py
class RedFlag(BaseModel):
    flag: str
    severity: Literal["low", "medium", "high"]
    evidence_snippet: str

class ExtractedJD(BaseModel):
    role_title: str
    required_skills: list[str]
    nice_to_have_skills: list[str]
    experience_band: Literal["junior", "mid", "senior", "staff+"]
    min_years_experience: int
    red_flags: list[RedFlag]
    confidence: float  # self-reported extraction confidence

# schemas/candidate.py
class ScoredCandidate(BaseModel):
    candidate_id: str
    semantic_similarity: float      # raw vector search score
    llm_rerank_score: float         # LLM re-ranking score
    final_score: float
    matched_skills: list[str]
    missing_skills: list[str]
    rationale: str

# schemas/outreach.py
class OutreachEmail(BaseModel):
    candidate_id: str
    subject: str
    body: str
    personalization_points: list[str]

# schemas/eval.py
class EvalResult(BaseModel):
    agent: str
    task_id: str
    relevance: float
    faithfulness: float
    completeness: float
    overall_confidence: float
    needs_human_review: bool
    review_reason: str | None
```

---

## 6. Orchestration Design (Custom, No Framework)

The Planner runs a small explicit **state machine** rather than a generic graph library:

```
PENDING → PLANNING → DISPATCHING → RUNNING → EVALUATING → (DONE | NEEDS_REVIEW | FAILED)
```

- **Planner** currently builds a **fixed task graph** (`extract_jd → score_candidates → draft_outreach`) representing the standard hiring pipeline. This is a deliberate design choice — the pipeline steps are well-defined and don't benefit from LLM-driven decomposition. The `TaskGraph` architecture supports future extension to dynamic planning (conditional tasks, re-planning on failure) if needed.
- Each task dispatch goes through `BaseAgent.run()`, which wraps: retry w/ exponential backoff → OpenTelemetry span → Pydantic validation of output → **G-Eval scoring** (LLM-as-judge).
- On task failure, the state machine retries with exponential backoff up to N times before marking `FAILED`.
- After each agent completes, G-Eval scores the output on relevance/faithfulness/completeness. If any dimension falls below the agent's threshold, the output is flagged for human review and an `eval_flagged` SSE event is emitted.
- State + progress is emitted as events (`events.py`) consumed by the SSE endpoint — the frontend sees exactly the state machine transitions and eval flags live.

---

## 7. MCP Server Layer

Three independent MCP servers, each a separate deployable process (stdio for local dev, Streamable HTTP for prod):

| Server | Tools Exposed | Backing System |
|---|---|---|
| `jd-parser-server` | `parse_raw_jd`, `normalize_skill_taxonomy` | Pure LLM + skill taxonomy lookup table |
| `candidate-db-server` | `vector_search_candidates`, `get_candidate_profile`, `upsert_candidate` | ChromaDB |
| `email-server` | `send_outreach_email`, `check_rate_limit` | Redis token bucket (rate limiting) + in-memory store |

> **Note on email-server:** Emails are currently stored in-memory rather than sent via SMTP. The rate-limiting (Redis token bucket) and MCP interface are production-ready — swap the `send_outreach_email` tool body for SMTP/SendGrid/SES in production.

Design rules: each tool is minimal and single-purpose (avoid sprawling do-everything tools), every tool call is treated as a security boundary (input validation + auth), and servers are versioned/pinned (e.g., `jd-parser-server:v1.0.0`) so schema drift doesn't silently break agents.

---

## 8. Evaluation Layer (G-Eval)

- Implements G-Eval's chain-of-thought scoring approach: the eval LLM is given the task definition + rubric, reasons step by step, then emits a numeric score per dimension.
- Dimensions scored per agent output: **relevance**, **faithfulness** (no hallucinated facts vs. source JD/candidate profile), **completeness**.
- Each agent type has its own threshold in `evaluation/thresholds.py` (e.g., JD Analyser faithfulness < 0.8 → flag).
- Flagged outputs are written to a `human_review_queue` table with the reason, original output, and eval rationale attached — never silently dropped or silently passed through.
- `tests/eval/` holds a golden set of ~20 JDs + expected extractions used as a regression suite — run this before every deploy.

---

## 9. Streaming (SSE) Design

- `GET /pipeline/{run_id}/stream` — Server-Sent Events endpoint.
- Event types: `state_change`, `agent_started`, `agent_completed`, `eval_flagged`, `run_completed`.
- Frontend renders a live timeline: "Planning...", "JD Analyser: extracted 8 skills (2.1s)", "Scoring 42 candidates...", "3 outputs flagged for review".

---

## 10. Data Model (PostgreSQL, sketch)

```
runs(id, goal_text, status, created_at, completed_at)
jds(id, run_id, raw_text, extracted_json, confidence)
candidates(id, profile_json, embedding_id)
scored_candidates(id, run_id, candidate_id, final_score, rationale_json)
outreach_emails(id, run_id, candidate_id, subject, body, sent_at, status)
eval_results(id, run_id, agent, task_id, relevance, faithfulness, completeness, needs_review)
human_reviews(id, eval_result_id, reviewer, decision, notes, reviewed_at)
```

---

## 11. Build Phases (Roadmap)

- [x] **Phase 0 — Scaffolding:** repo structure, `docker-compose` (Postgres/Redis/Chroma), config + provider-agnostic LLM adapter, base agent class with tracing/retry.
- [x] **Phase 1 — JD Analyser:** Pydantic schemas, `jd-parser-server` MCP, prompt + eval golden set, unit tests (target ≥97% field accuracy on your 50-JD test set).
- [x] **Phase 2 — Candidate Scorer:** ChromaDB setup, `candidate-db-server` MCP, embedding pipeline, semantic search + LLM re-rank step.
- [x] **Phase 3 — Outreach Drafter:** `email-server` MCP, Redis rate limiter, personalized template generation.
- [x] **Phase 4 — Planner + Orchestration:** task graph, state machine, dispatch logic, retry/re-plan behavior.
- [x] **Phase 5 — Evaluation Layer:** G-Eval implementation, thresholds, human review queue.
- [x] **Phase 6 — API + Streaming:** FastAPI routes, SSE event stream, review endpoints.
- [x] **Phase 7 — Observability + Hardening:** OpenTelemetry wiring, structured logging, load test the pipeline, security pass on MCP servers.
- [x] **Phase 8 — Polish:** README/demo script, sample dataset, deploy config.

We'll build phase by phase so context stays manageable — each phase produces working, tested code before moving to the next.

---

## 12. Environment Variables (`.env.example`)

```
# LLM provider-agnostic config
LLM_PROVIDER=anthropic            # anthropic | openai | ...
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Infra
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/hiring
REDIS_URL=redis://localhost:6379/0
CHROMA_PERSIST_DIR=./data/chroma

# Rate limiting
EMAIL_SEND_RATE_PER_MINUTE=10

# Eval thresholds
EVAL_MIN_CONFIDENCE=0.75

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=
```

---

## 13. What "Production Grade" Means Here (Checklist)

- Every agent I/O validated with Pydantic — no raw string passing between agents.
- Every external call (LLM, MCP tool, DB) wrapped with retry + timeout + tracing span.
- No silent failures: every error path either retries, re-plans, or surfaces to human review.
- MCP servers versioned and schema-tested in CI (fail build on tool schema drift).
- Rate limiting enforced before hitting external APIs, not after failure.
- Eval golden set run in CI before merge — no regression in extraction/scoring accuracy.
- Structured logging + tracing correlated by `run_id` across all agents and MCP servers.
- Secrets only via environment/config, never hardcoded.

---


## Quick Start: How to Run the Project

Follow these steps to spin up the entire pipeline locally:

1. **Install Dependencies**
   We use `uv` for lightning-fast package management:
   ```bash
   uv sync
   ```

2. **Set Up the Environment**
   Copy the example environment file and fill in your API keys (e.g., OpenAI or Gemini):
   ```bash
   cp .env.example .env
   ```

3. **Start the Infrastructure (Optional)**
   If you have Docker, you can spin up Postgres, Redis, and ChromaDB:
   ```bash
   docker-compose up -d
   ```
   *(Note: The system falls back to SQLite and local Chroma if Postgres/Redis are absent).*

4. **Run Database Migrations**
   Initialize the database schema (including the HR Authentication tables):
   ```bash
   PYTHONPATH=. uv run alembic upgrade head
   ```

5. **Seed the Database (Optional but Recommended)**
   Load some mock candidates and standard email templates into ChromaDB:
   ```bash
   PYTHONPATH=. uv run python scripts/seed_candidates.py
   PYTHONPATH=. uv run python scripts/seed_templates.py
   ```

6. **Start the FastAPI Backend & Frontend**
   Run the Uvicorn server (which serves the API and the static frontend):
   ```bash
   PYTHONPATH=. uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```

7. **Access the Application**
   Open your browser and navigate to:
   [http://localhost:8080](http://localhost:8080)

   *Since this is a secure HR platform, you must click **Register** to create an account with a secure password the first time you visit!*

---
## 15. Switching LLM Providers & Models

The pipeline uses a **provider-agnostic adapter layer** in [`app/llm/provider_adapter.py`](app/llm/provider_adapter.py). All you need to do is update two values in your `.env` file and optionally install the relevant SDK. No agent code changes required.

### Quick Reference

| Provider | `LLM_PROVIDER` value | Required env var | SDK |
|---|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` | Included |
| Google Gemini | `gemini` | `GEMINI_API_KEY` | Included (`google-genai`) |
| Anthropic | `anthropic` *(see below)* | `ANTHROPIC_API_KEY` | Add yourself |

---

### Switching to OpenAI

1. Edit `.env`:
   ```env
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-proj-...
   ```

2. Optionally change the default model in `provider_adapter.py`:
   ```python
   self.default_model = "gpt-4o-mini"   # fast + cheap
   # or
   self.default_model = "gpt-4o"        # higher quality
   ```

3. Restart the server — no other changes needed.

> **Note:** `gpt-4o-mini` is recommended for cost/speed balance. Use `gpt-4o` for higher-stakes production extraction. The pipeline uses OpenAI's **structured outputs** API (`response_format=Model`) which enforces strict Pydantic schema compliance.

---

### Switching to Google Gemini

1. Edit `.env`:
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=AQ.xxxxx
   ```

2. Optionally change the default model in `provider_adapter.py`:
   ```python
   self.default_model = "gemini-3.1-flash-lite"   # fast free-tier
   # or
   self.default_model = "gemini-3.1-flash"         # balanced
   # or
   self.default_model = "gemini-3.1-pro-preview"   # highest quality
   ```

3. Restart the server.

> **Gemini model notes:**
> - Free-tier quotas are **per model** — if one model is rate-limited, try another.
> - The adapter uses **prompt-based JSON extraction** (not native function calling), so all models are compatible.
> - You can list all available models for your key with:
>   ```bash
>   PYTHONPATH=. uv run python -c "
>   from google import genai
>   from app.config import settings
>   c = genai.Client(api_key=settings.GEMINI_API_KEY)
>   for m in c.models.list():
>       if 'generateContent' in m.supported_actions:
>           print(m.name)
>   "
>   ```

---

### Adding a New Provider (e.g. Anthropic)

The adapter pattern makes this straightforward. Add a new class to [`app/llm/provider_adapter.py`](app/llm/provider_adapter.py):

```python
class AnthropicAdapter(LLMProviderAdapter):
    def __init__(self):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.default_model = "claude-sonnet-4-5"

    async def generate_structured_output(self, prompt, response_model, system_prompt=None, model_name=None):
        import json
        model_to_use = model_name or self.default_model
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        full_prompt = f"{system_prompt or ''}\n\n{prompt}\n\nRespond ONLY with valid JSON matching:\n```json\n{schema_json}\n```"

        message = await self.client.messages.create(
            model=model_to_use,
            max_tokens=2048,
            messages=[{"role": "user", "content": full_prompt}]
        )
        data = json.loads(message.content[0].text.strip())
        return response_model(**data)
```

Then register it in the factory:
```python
def get_llm_provider() -> LLMProviderAdapter:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai":   return OpenAIAdapter()
    if provider == "gemini":   return GeminiAdapter()
    if provider == "anthropic": return AnthropicAdapter()   # <-- add this line
    raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")
```

Install the SDK:
```bash
uv add anthropic
```

Update `.env`:
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
```

---

### Per-Agent Model Overrides

By default all agents use the model set in the adapter's `__init__`. If you want a specific agent to use a different (more powerful) model, pass `model_name` when calling `generate_structured_output`:

```python
# In any agent or MCP server:
result = await llm.generate_structured_output(
    prompt=raw_text,
    response_model=ExtractedJD,
    system_prompt=system_prompt,
    model_name="gpt-4o"   # override just for this call
)
```

This is useful for tuning the cost/quality tradeoff per task — for example, using a small model for JD extraction but a larger one for the G-Eval evaluation layer.
