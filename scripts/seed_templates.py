import asyncio
import sys
from app.infra.vector_store import vector_store

def seed():
    templates = [
        {
            "id": "reach_out_1",
            "intent": "standard reach out for a candidate whose skills match perfectly",
            "text": "Subject: Opportunity at [Company Name]\n\nHi {candidate_name},\n\nI was reviewing your profile and was really impressed by your background, particularly your experience with {matched_skills}. We are currently looking for someone with your skill set for an open role.\n\nAre you open to a quick chat this week?\n\nBest,\n[HR Name]"
        },
        {
            "id": "rejection_1",
            "intent": "polite rejection for a candidate who is missing required skills",
            "text": "Subject: Update on your application to [Company Name]\n\nHi {candidate_name},\n\nThank you for taking the time to apply and share your experience with us. After careful consideration, we have decided to move forward with other candidates who have more direct experience with {missing_skills}.\n\nWe will keep your resume on file for future openings that match your profile.\n\nBest,\nThe Recruiting Team"
        },
        {
            "id": "follow_up_1",
            "intent": "follow up with a candidate who hasn't replied",
            "text": "Subject: Following up: Opportunity at [Company Name]\n\nHi {candidate_name},\n\nI wanted to float this to the top of your inbox. Are you still open to discussing the role?\n\nLet me know if you have a few minutes to connect.\n\nBest,\n[HR Name]"
        }
    ]
    
    for t in templates:
        vector_store.upsert_template(t["id"], t["intent"], t["text"])
        print(f"Seeded template {t['id']}")

if __name__ == "__main__":
    seed()
