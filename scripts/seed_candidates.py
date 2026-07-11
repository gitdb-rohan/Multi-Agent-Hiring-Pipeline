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
            current_title="Senior Backend Engineer",
            skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
            years_of_experience=6,
            summary="Experienced backend engineer with a strong focus on scalable APIs and microservices."
        ),
        CandidateProfile(
            id="cand_002",
            name="Bob Jones",
            current_title="Frontend Developer",
            skills=["JavaScript", "React", "CSS", "HTML"],
            years_of_experience=3,
            summary="Passionate frontend dev, loves building beautiful UIs but has limited backend exposure."
        ),
        CandidateProfile(
            id="cand_003",
            name="Charlie Brown",
            current_title="Full Stack Developer",
            skills=["Python", "Django", "React", "PostgreSQL"],
            years_of_experience=4,
            summary="Full stack engineer comfortable across the stack, mostly using Django."
        ),
        CandidateProfile(
            id="cand_004",
            name="Diana Prince",
            current_title="Lead Platform Engineer",
            skills=["Go", "Kubernetes", "AWS", "Python", "Terraform"],
            years_of_experience=10,
            summary="Platform engineer focused on infra and tooling. Writes Go and Python."
        ),
        CandidateProfile(
            id="cand_005",
            name="Evan Wright",
            current_title="Junior Developer",
            skills=["Python", "Flask"],
            years_of_experience=1,
            summary="Recent bootcamp grad eager to learn backend development."
        )
    ]
    
    logger.info(f"Seeding {len(candidates)} candidates...")
    for c in candidates:
        vector_store.upsert_candidate(
            candidate_id=c.id,
            document=c.to_embedding_text(),
            metadata={"name": c.name, "years_of_experience": c.years_of_experience}
        )
    
    logger.info("Seeding complete.")

if __name__ == "__main__":
    seed()
