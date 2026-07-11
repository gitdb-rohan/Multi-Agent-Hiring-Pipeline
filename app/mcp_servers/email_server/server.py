import json
import logging
import asyncio
from mcp.server.fastmcp import FastMCP
from app.infra.redis_client import email_rate_limiter

# Initialize FastMCP server
mcp = FastMCP("email-server")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email-server")

# In-memory store for sent emails (in production this would be a real SMTP/API call)
sent_emails: list[dict] = []


@mcp.tool()
async def send_outreach_email(candidate_id: str, subject: str, body: str) -> str:
    """
    Sends a personalized outreach email to a candidate.
    Rate-limited via Redis token bucket. In this implementation, emails are
    stored in-memory rather than sent via SMTP (swap for production).
    Returns a JSON status object.
    """
    logger.info(f"Attempting to send email to candidate {candidate_id}...")

    # Check rate limit before sending
    allowed = await email_rate_limiter.acquire()
    if not allowed:
        logger.warning(f"Rate limited: cannot send email to {candidate_id}")
        return json.dumps({
            "status": "rate_limited",
            "candidate_id": candidate_id,
            "message": "Rate limit exceeded. Try again later."
        })

    # Simulate sending (in production: SMTP / SendGrid / SES call)
    email_record = {
        "candidate_id": candidate_id,
        "subject": subject,
        "body": body,
        "status": "sent",
    }
    sent_emails.append(email_record)
    logger.info(f"Email sent to candidate {candidate_id}: {subject}")

    return json.dumps({
        "status": "sent",
        "candidate_id": candidate_id,
        "subject": subject,
    })


@mcp.tool()
async def check_rate_limit() -> str:
    """
    Checks the current email sending rate limit status.
    Returns the number of remaining tokens in the bucket.
    """
    remaining = await email_rate_limiter.check_remaining()
    return json.dumps({
        "remaining_tokens": remaining,
        "max_per_minute": email_rate_limiter.max_tokens,
    })


if __name__ == "__main__":
    mcp.run()
