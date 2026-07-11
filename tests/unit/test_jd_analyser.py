import pytest
from app.schemas.jd import ExtractedJD, RedFlag

def test_extracted_jd_validation():
    # Valid data
    valid_data = {
        "role_title": "Senior Backend Engineer",
        "required_skills": ["Python", "FastAPI"],
        "nice_to_have_skills": ["Docker", "Kubernetes"],
        "experience_band": "senior",
        "min_years_experience": 5,
        "red_flags": [
            {
                "flag": "Long hours implied",
                "severity": "medium",
                "evidence_snippet": "We work hard and play hard"
            }
        ],
        "confidence": 0.95
    }
    
    jd = ExtractedJD(**valid_data)
    assert jd.role_title == "Senior Backend Engineer"
    assert len(jd.red_flags) == 1
    assert jd.red_flags[0].severity == "medium"

def test_extracted_jd_invalid_experience_band():
    invalid_data = {
        "role_title": "Engineer",
        "required_skills": [],
        "nice_to_have_skills": [],
        "experience_band": "expert", # Invalid
        "min_years_experience": 10,
        "red_flags": [],
        "confidence": 0.9
    }
    
    with pytest.raises(ValueError):
        ExtractedJD(**invalid_data)
