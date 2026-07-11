# Architectural Challenges & Solutions

Building a multi-agent system (MAS) with a strict "human-in-the-loop" constraint and production-grade reliability introduces several unique challenges compared to a standard web app or a simple LLM script.

## 1. Ensuring LLM Output Reliability
**Challenge**: Agents passing natural language text between each other is highly brittle. If the JD Analyser output format changes slightly, the Candidate Scorer fails to parse it. Furthermore, LLMs hallucinate requirements not present in the text.
**Solution**: 
- **Strict Pydantic Contracts**: We utilized the `openai` SDK's structured outputs (`response_format`) bound to strict Pydantic schemas (`app/schemas/`). If the LLM output violates the schema, it fails the parse step and triggers our retry logic.
- **LLM-as-a-Judge (G-Eval)**: Instead of assuming the data is correct, we built a dedicated Evaluation Layer (`app/evaluation/geval.py`). Every agent output is evaluated on a 0-1 scale for Relevance, Faithfulness, and Completeness. If Faithfulness drops below a threshold (e.g. 0.8), it is pushed to a Human Review Queue before proceeding.

## 2. Dealing with Rate Limits and Non-Deterministic Delays
**Challenge**: AI APIs (OpenAI/Anthropic) are heavily rate-limited. Outreach email APIs (SMTP/SendGrid) are also rate-limited. Firing 10 agent threads concurrently will lead to 429 Too Many Requests errors.
**Solution**: 
- **Token Bucket Limiter**: We implemented a Redis-backed Lua-script token bucket (`app/infra/redis_client.py`). Before the `email-server` MCP sends an email, it acquires a token. This guarantees we don't exceed the configured `EMAIL_SEND_RATE_PER_MINUTE`.
- **Exponential Backoff**: The `BaseAgent` class includes an asynchronous `@with_retry` decorator. If a rate limit or transient network error occurs, the agent pauses and retries.

## 3. Tool Boundary Security & Standardization (MCP)
**Challenge**: Agents having raw access to databases and SMTP servers is a security risk and couples the agent logic to the infrastructure. 
**Solution**:
- We utilized the **Model Context Protocol (MCP)**. We built three distinct FastMCP servers: `jd-parser-server`, `candidate-db-server`, and `email-server`.
- The agents communicate with these servers via standard IO (stdio). This creates a strict boundary: the agents only know the MCP tool interface, and the MCP servers handle all DB/Network auth. This means the `candidate-db-server` could be swapped from ChromaDB to Pinecone without touching the agent code.

## 4. Orchestration without Lock-In
**Challenge**: Using heavy frameworks like LangGraph often leads to lock-in and makes custom Human-in-the-Loop interventions difficult.
**Solution**:
- We built a custom explicit State Machine (`app/orchestration/state_machine.py`) that steps through a Directed Acyclic Graph (DAG) of tasks (`TaskGraph`). 
- This gives us full control over pausing execution for the `needs_review` state and allows us to easily stream `Server-Sent Events (SSE)` to the frontend for a live view of the pipeline.

## 5. UI Streaming UX
**Challenge**: Pipeline runs take 30-90 seconds. A simple loading spinner is terrible UX.
**Solution**:
- We built an Event Emitter that hooks into the State Machine. Every time an agent starts, finishes, or gets flagged by G-Eval, an SSE event is fired. The Vanilla JS frontend listens to these events and constructs a live timeline of operations, completely removing the "black box" feeling of AI pipelines.
