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

        # 3. Seed Candidate Records + Linked Interviews (Potential Matches)
        # Each candidate gets a row in `candidates` and a linked `interviews` row.
        candidates = [
            {
                "name": "Alice High-Match",
                "email": "alice@example.com",
                "skills": ["Python", "Go", "distributed systems", "ownership mindset"],
                "experience_years": 6,
                "score": 92,
                "rec": "strong_pass",
                "summary": "Candidate clearly demonstrated ownership in past roles. Very aligned with shipping speed and hates bureaucracy.",
                "clarity": 95,
                "energy": 90,
                "conv_completeness": 91,
                "conv_depth": 88,
            },
            {
                "name": "Bob Good-Fit",
                "email": "bob@example.com",
                "skills": ["React", "TypeScript", "product thinking", "user research"],
                "experience_years": 4,
                "score": 85,
                "rec": "pass",
                "summary": "Good technical skills, values user feedback. Slightly more process-oriented but expressed willingness to adapt.",
                "clarity": 88,
                "energy": 85,
                "conv_completeness": 84,
                "conv_depth": 82,
            },
            {
                "name": "Charlie Mismatch",
                "email": "charlie@example.com",
                "skills": ["Java", "enterprise architecture", "process design"],
                "experience_years": 8,
                "score": 60,
                "rec": "borderline",
                "summary": "Technically sound but prefers long planning cycles. Explicitly asked for a 'structured' environment with clear hierarchy.",
                "clarity": 70,
                "energy": 60,
                "conv_completeness": 65,
                "conv_depth": 58,
            },
            {
                "name": "David No-Go",
                "email": "david@example.com",
                "skills": ["C#", ".NET", "waterfall methodology"],
                "experience_years": 10,
                "score": 45,
                "rec": "fail",
                "summary": "Looking for a very rigid environment. Stated dislike for ambiguity and rapid changes. Not a culture fit.",
                "clarity": 80,
                "energy": 40,
                "conv_completeness": 50,
                "conv_depth": 42,
            },
            {
                "name": "Eve Innovator",
                "email": "eve@example.com",
                "skills": ["Rust", "systems programming", "startup experience", "user research", "rapid prototyping"],
                "experience_years": 5,
                "score": 95,
                "rec": "strong_pass",
                "summary": "Thrives in chaos. Built a startup previously. Deeply user-focused.",
                "clarity": 92,
                "energy": 95,
                "conv_completeness": 94,
                "conv_depth": 92,
            }
        ]

        print(f"Seeding {len(candidates)} candidates with linked interviews...")
        for i, cand in enumerate(candidates):
            # Create parsed_data for culture matching
            parsed_data = {
                "work_style": "autonomous" if cand["score"] >= 80 else "structured",
                "collaboration": "high" if cand["energy"] >= 80 else "moderate",
                "pace_preference": "fast" if cand["score"] >= 80 else "methodical",
                "values": ["ownership", "shipping", "user_focus"] if cand["score"] >= 80 else ["process", "stability", "hierarchy"],
                "summary": cand["summary"],
            }

            # Insert or get candidate record
            existing_candidate = await conn.fetchrow(
                "SELECT id FROM candidates WHERE email = $1",
                cand["email"]
            )
            if existing_candidate:
                candidate_id = existing_candidate["id"]
                print(f"  Found existing candidate: {cand['name']} ({candidate_id})")
            else:
                candidate_row = await conn.fetchrow("""
                    INSERT INTO candidates (name, email, skills, experience_years, parsed_data)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """,
                    cand["name"],
                    cand["email"],
                    json.dumps(cand["skills"]),
                    cand["experience_years"],
                    json.dumps(parsed_data),
                )
                candidate_id = candidate_row["id"]
                print(f"  Created candidate: {cand['name']} ({candidate_id})")

            # Build screening analysis
            screening_analysis = {
                "communication_clarity": {"score": cand["clarity"], "evidence": [], "notes": "Clear speaker"},
                "engagement_energy": {"score": cand["energy"], "evidence": [], "notes": "Energy level varies"},
                "critical_thinking": {"score": cand["score"], "evidence": [], "notes": "Logic check"},
                "professionalism": {"score": 90, "evidence": [], "notes": "Professional"},
                "overall_score": cand["score"],
                "recommendation": cand["rec"],
                "summary": cand["summary"],
                "analyzed_at": datetime.now().isoformat()
            }

            # Build conversation analysis
            conversation_analysis = {
                "coverage_completeness": {
                    "overall_score": cand["conv_completeness"],
                    "dimensions_covered": ["autonomy", "pace", "values"] if cand["score"] >= 80 else ["process", "stability"],
                    "dimensions_missed": [],
                    "coverage_details": {}
                },
                "response_depth": {
                    "overall_score": cand["conv_depth"],
                    "specific_examples_count": 4 if cand["score"] >= 80 else 2,
                    "vague_responses_count": 0 if cand["score"] >= 80 else 2,
                    "response_analysis": []
                },
                "missed_opportunities": [],
                "prompt_improvement_suggestions": [],
                "interview_summary": cand["summary"],
                "analyzed_at": datetime.now().isoformat()
            }

            # Check for existing interview linked to this candidate
            existing_interview = await conn.fetchrow(
                "SELECT id FROM interviews WHERE candidate_id = $1 AND company_id = $2 AND interview_type = 'candidate'",
                candidate_id, company_id
            )
            if existing_interview:
                print(f"  Interview already linked for {cand['name']}, updating...")
                await conn.execute("""
                    UPDATE interviews
                    SET screening_analysis = $1, conversation_analysis = $2, status = 'completed'
                    WHERE id = $3
                """, json.dumps(screening_analysis), json.dumps(conversation_analysis), existing_interview["id"])
            else:
                await conn.execute("""
                    INSERT INTO interviews (
                        company_id, candidate_id, interviewer_name, interview_type,
                        screening_analysis, conversation_analysis, status, created_at, completed_at
                    )
                    VALUES ($1, $2, $3, 'candidate', $4, $5, 'completed', NOW(), NOW())
                """,
                    company_id,
                    candidate_id,
                    cand["name"],
                    json.dumps(screening_analysis),
                    json.dumps(conversation_analysis),
                )
                print(f"  Created interview for {cand['name']}")

        print("\nSeed complete! Matcha-Tech is ready for multi-signal ranking.")
        print(f"Company ID: {company_id}")
        print("Run POST /companies/{company_id}/rankings/run to generate rankings.")

    await close_pool()

if __name__ == '__main__':
    asyncio.run(seed_matcha_tech())
