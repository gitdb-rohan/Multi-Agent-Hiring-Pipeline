import asyncio
import logging
from app.agents.jd_analyser import JDAnalyser, JDAnalyserRequest

logging.basicConfig(level=logging.INFO)

async def main():
    jd_text = """
    We are looking for a Rockstar Backend Developer to join our fast-paced startup!
    You will be working heavily with Python, FastAPI, and Postgres.
    We need someone with at least 4 years of experience.
    Nice to have: Docker and AWS.
    Be prepared to work hard and play hard, sometimes weekends are expected but we have free pizza!
    """
    
    agent = JDAnalyser()
    request = JDAnalyserRequest(raw_text=jd_text)
    
    try:
        result = await agent.run(request)
        print("\n--- EXTRACTION RESULT ---")
        print(result.model_dump_json(indent=2))
        print("-------------------------\n")
    except Exception as e:
        print(f"Extraction failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
