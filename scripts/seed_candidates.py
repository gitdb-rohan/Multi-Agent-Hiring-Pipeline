import logging
from app.schemas.candidate import CandidateProfile
from app.infra.vector_store import vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed():
    candidates = [
        CandidateProfile(
            id="cand_001",
            name="Alice Smith",
            email="alice.smith@example.com",
            current_title="Senior Backend Engineer",
            skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
            years_of_experience=6,
            previous_companies=["Stripe", "Dropbox"],
            projects=["Payment gateway microservice", "Real-time notification system"],
            summary="Experienced backend engineer with a strong focus on scalable APIs and microservices."
        ),
        CandidateProfile(
            id="cand_002",
            name="Bob Jones",
            email="bob.jones@example.com",
            current_title="Frontend Developer",
            skills=["JavaScript", "React", "CSS", "HTML"],
            years_of_experience=3,
            previous_companies=["Shopify"],
            projects=["E-commerce dashboard redesign"],
            summary="Passionate frontend dev, loves building beautiful UIs but has limited backend exposure."
        ),
        CandidateProfile(
            id="cand_003",
            name="Charlie Brown",
            email="charlie.brown@example.com",
            current_title="Full Stack Developer",
            skills=["Python", "Django", "React", "PostgreSQL"],
            years_of_experience=4,
            previous_companies=["Atlassian", "Canva"],
            projects=["Internal analytics platform", "CI/CD pipeline automation"],
            summary="Full stack engineer comfortable across the stack, mostly using Django."
        ),
        CandidateProfile(
            id="cand_004",
            name="Diana Prince",
            email="diana.prince@example.com",
            current_title="Lead Platform Engineer",
            skills=["Go", "Kubernetes", "AWS", "Python", "Terraform"],
            years_of_experience=10,
            previous_companies=["Google", "Netflix", "Hashicorp"],
            projects=["Multi-region Kubernetes platform", "Infrastructure cost optimization tool"],
            summary="Platform engineer focused on infra and tooling. Writes Go and Python."
        ),
        CandidateProfile(
            id="cand_005",
            name="Evan Wright",
            email="evan.wright@example.com",
            current_title="Junior Developer",
            skills=["Python", "Flask"],
            years_of_experience=1,
            previous_companies=[],
            projects=["Personal blog with Flask", "Weather API wrapper"],
            summary="Recent bootcamp grad eager to learn backend development."
        )
    ]
    
    logger.info(f"Seeding {len(candidates)} candidates...")
    for c in candidates:
        vector_store.upsert_candidate(
            candidate_id=c.id,
            document=c.to_embedding_text(),
            metadata=c.to_chroma_metadata()
        )
    
    logger.info("Seeding complete.")

if __name__ == "__main__":
    seed()

