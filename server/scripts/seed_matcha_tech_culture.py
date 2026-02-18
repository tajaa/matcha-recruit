"""
Seed script to populate Matcha-Tech company data for Tutor matching logic.
Run with: python -m scripts.seed_matcha_tech_culture
"""
import asyncio
import sys
import os
import json
from datetime import datetime, timedelta
import random

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.database import init_pool, close_pool, get_connection

async def seed_matcha_tech():
    print("Initializing...")
    settings = load_settings()
    await init_pool(settings.database_url)

    async with get_connection() as conn:
        # 1. Create or Get "Matcha-Tech" Company
        company_name = "Matcha-Tech"
        company = await conn.fetchrow("SELECT id, name FROM companies WHERE name = $1", company_name)

        if not company:
            print(f"Creating company: {company_name}...")
            # We need to make sure we use a valid UUID if ID is not auto-generated, usually it is DEFAULT gen_random_uuid()
            # Checking seed_employees.py, it uses RETURNING id, so it's likely auto-generated.
            company = await conn.fetchrow("""
                INSERT INTO companies (name, industry, size)
                VALUES ($1, 'Technology', 'startup')
                RETURNING id, name
            """, company_name)
        else:
            print(f"Found company: {company_name}")

        company_id = company['id']
        print(f"Using Company ID: {company_id}")

        # 2. Seed Culture Interviews (The "Standard")
        # These define the company's baseline culture.
        culture_interviews = [
            {
                "interviewer_name": "CTO",
                "summary": "We value extreme ownership and rapid shipping. Mistakes are fine if fixed quickly. We dislike bureaucracy.",
                "completeness": 95,
                "depth": 90,
            },
            {
                "interviewer_name": "Head of Product",
                "summary": "User-centric design is key. We don't build features without validating demand first. Open debate is encouraged.",
                "completeness": 88,
                "depth": 85,
            },
            {
                "interviewer_name": "Lead Engineer",
                "summary": "Flat hierarchy. Junior engineers should feel comfortable challenging seniors if they have data.",
                "completeness": 92,
                "depth": 88,
            }
        ]

        print(f"Seeding {len(culture_interviews)} culture interviews...")
        for interview in culture_interviews:
            analysis = {
                "coverage_completeness": {
                    "overall_score": interview["completeness"],
                    "dimensions_covered": ["autonomy", "speed", "user_focus", "transparency"],
                    "dimensions_missed": [],
                    "coverage_details": {
                        "autonomy": {"covered": True, "depth": "deep", "evidence": "Mentioned ownership multiple times"}
                    }
                },
                "response_depth": {
                    "overall_score": interview["depth"],
                    "specific_examples_count": 5,
                    "vague_responses_count": 0,
                    "response_analysis": []
                },
                "missed_opportunities": [],
                "prompt_improvement_suggestions": [],
                "interview_summary": interview["summary"],
                "analyzed_at": datetime.now().isoformat()
            }
            
            await conn.execute("""
                INSERT INTO interviews (
                    company_id, interviewer_name, interview_type, 
                    conversation_analysis, status, created_at, completed_at
                )
                VALUES ($1, $2, 'culture', $3, 'completed', NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day')
            """, company_id, interview["interviewer_name"], json.dumps(analysis))

        # 3. Seed Candidate Interviews (Potential Matches)
        # These represent "Applicant" interviews that need to be scored against the culture.
        candidates = [
            {
                "name": "Alice High-Match",
                "score": 92,
                "rec": "strong_pass",
                "summary": "Candidate clearly demonstrated ownership in past roles. Very aligned with shipping speed and hates bureaucracy.",
                "clarity": 95,
                "energy": 90
            },
            {
                "name": "Bob Good-Fit",
                "score": 85,
                "rec": "pass",
                "summary": "Good technical skills, values user feedback. Slightly more process-oriented but expressed willingness to adapt.",
                "clarity": 88,
                "energy": 85
            },
            {
                "name": "Charlie Mismatch",
                "score": 60,
                "rec": "borderline",
                "summary": "Technically sound but prefers long planning cycles. Explicitly asked for a 'structured' environment with clear hierarchy.",
                "clarity": 70,
                "energy": 60
            },
            {
                "name": "David No-Go",
                "score": 45,
                "rec": "fail",
                "summary": "Looking for a very rigid environment. Stated dislike for ambiguity and rapid changes. Not a culture fit.",
                "clarity": 80,
                "energy": 40
            },
            {
                "name": "Eve Innovator",
                "score": 95,
                "rec": "strong_pass",
                "summary": "Thrives in chaos. Built a startup previously. Deeply user-focused.",
                "clarity": 92,
                "energy": 95
            }
        ]

        print(f"Seeding {len(candidates)} candidate interviews...")
        for i, cand in enumerate(candidates):
            # Create analysis
            analysis = {
                "communication_clarity": {"score": cand["clarity"], "evidence": [], "notes": "Clear speaker"},
                "engagement_energy": {"score": cand["energy"], "evidence": [], "notes": "Energy level varies"},
                "critical_thinking": {"score": cand["score"], "evidence": [], "notes": "Logic check"},
                "professionalism": {"score": 90, "evidence": [], "notes": "Professional"},
                "overall_score": cand["score"],
                "recommendation": cand["rec"],
                "summary": cand["summary"],
                "analyzed_at": datetime.now().isoformat()
            }

            # Insert interview
            # We don't have a 'candidate_name' column in interviews table usually, 
            # maybe 'interviewer_name' is used for the candidate name in this context? 
            # Or maybe it's just anonymous. I'll put the candidate name in 'interviewer_name' for now to identify them
            # or just leave it null if strictly for interviewer.
            # Looking at models, 'interviewer_name' is optional. 
            # But for a candidate interview, usually we link to a 'candidate_id' if that table exists.
            # Let's check candidate models later. For now, we seed the interview data.
            # I'll put candidate name in interviewer_name field just for visibility in admin list.
            
            await conn.execute("""
                INSERT INTO interviews (
                    company_id, interviewer_name, interview_type, 
                    screening_analysis, status, created_at, completed_at
                )
                VALUES ($1, $2, 'candidate', $3, 'completed', NOW(), NOW())
            """, company_id, cand["name"], json.dumps(analysis))

        print("Seed complete! Matcha-Tech is ready for matching logic.")

    await close_pool()

if __name__ == '__main__':
    asyncio.run(seed_matcha_tech())
