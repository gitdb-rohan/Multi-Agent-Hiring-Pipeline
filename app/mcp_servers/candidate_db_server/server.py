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

if __name__ == "__main__":
    # Run the server on stdio
    mcp.run()
