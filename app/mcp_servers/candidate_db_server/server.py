import sys
import json
import logging
from mcp.server.fastmcp import FastMCP
from app.infra.vector_store import vector_store

# Initialize FastMCP server
mcp = FastMCP("candidate-db-server")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("candidate-db-server")

@mcp.tool()
async def vector_search_candidates(query: str, top_k: int = 5) -> str:
    """
    Searches the vector database for candidates matching the semantic query.
    Returns a JSON string containing a list of matched candidates with their similarity scores.
    """
    logger.info(f"Searching candidates for query: {query[:50]}...")
    try:
        results = vector_store.search_candidates(query=query, top_k=top_k)
        return json.dumps(results)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return json.dumps({"error": str(e)})

@mcp.tool()
async def get_candidate_profile(candidate_id: str) -> str:
    """
    Retrieves the raw profile of a specific candidate by their ID.
    """
    try:
        result = vector_store.get_candidate(candidate_id)
        if result:
            return json.dumps(result)
        return json.dumps({"error": "Candidate not found"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def upsert_candidate(candidate_id: str, document: str, metadata_json: str) -> str:
    """
    Upserts a candidate into the vector database.
    If a candidate with the same ID already exists, their entry is replaced entirely.
    This enables dedup: use a deterministic ID (e.g. derived from email) and re-submitting
    a candidate automatically overwrites the old entry.

    Args:
        candidate_id: Unique identifier for the candidate.
        document: Text representation of the candidate for embedding.
        metadata_json: JSON string of metadata (name, email, years_of_experience, etc.)
    """
    try:
        metadata = json.loads(metadata_json)
        vector_store.upsert_candidate(
            candidate_id=candidate_id,
            document=document,
            metadata=metadata,
        )
        return json.dumps({"status": "upserted", "candidate_id": candidate_id})
    except Exception as e:
        logger.error(f"Upsert failed for {candidate_id}: {e}")
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    # Run the server on stdio
    mcp.run()
