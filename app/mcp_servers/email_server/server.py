import json
import logging
import asyncio
import os
import smtplib
from email.message import EmailMessage
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

    # SMTP Configuration
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT", "587")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    sender_email = os.environ.get("SMTP_SENDER", "hiring@company.com")
    
    # We simulate candidate email via their ID if no real email is known, 
    # but in a real system we would pass the candidate's email address here.
    # For now, we will use a dummy domain if we just have the ID.
    recipient_email = f"{candidate_id}@example.com"

    try:
        if smtp_host and smtp_user and smtp_pass:
            # Real SMTP Sending
            msg = EmailMessage()
            msg.set_content(body)
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = recipient_email

            logger.info(f"Connecting to SMTP server {smtp_host}:{smtp_port}...")
            with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                
            logger.info(f"Real email successfully sent via SMTP to {recipient_email}")
        else:
            # Simulated Sending (Fallback)
            logger.warning(f"SMTP credentials not found in env. Simulating email to {recipient_email}")
            
        email_record = {
            "candidate_id": candidate_id,
            "subject": subject,
            "body": body,
            "status": "sent",
        }
        sent_emails.append(email_record)
        
        return json.dumps({
            "status": "sent",
            "candidate_id": candidate_id,
            "subject": subject,
        })
    except Exception as e:
        logger.error(f"Failed to send email to {candidate_id}: {e}")
        return json.dumps({
            "status": "error",
            "candidate_id": candidate_id,
            "message": str(e)
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
