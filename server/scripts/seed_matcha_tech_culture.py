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

        # 3. Seed Culture Profile directly (avoids Gemini call during seeding)
        matcha_tech_culture_profile = {
            "collaboration_style": "High-trust, low-process. Teams self-organize around outcomes rather than tasks. Cross-functional pairing is encouraged; long approval chains are not.",
            "communication": "Direct and async-first. Slack for quick pings, written docs for decisions. Meetings are rare and must have clear owners and outcomes.",
            "pace": "Fast. Ship early, iterate quickly, fix mistakes in the open. Weekly releases are the norm; quarterly roadmaps are loose guides.",
            "hierarchy": "Flat. Job titles exist for external signaling only. Authority comes from context and judgment, not seniority. Junior engineers are expected to push back with data.",
            "values": ["extreme ownership", "user-centricity", "radical transparency", "bias for action", "curiosity"],
            "work_life_balance": "Sustainable intensity. High output is expected but burnout is actively discouraged. Flexible hours with team-agreed core overlap.",
            "growth_focus": "Individual ownership of growth. Monthly 1-on-1s with managers, but engineers define their own learning paths. Internal mobility is encouraged.",
            "decision_making": "Decentralized. Anyone can propose a change with a short written pitch. Decisions default to the person closest to the problem.",
            "remote_policy": "Remote-first with optional co-working spaces. Two company offsites per year for in-person collaboration.",
            "team_size": "Small, focused squads of 3–6. Each squad owns a full surface area end-to-end.",
            "key_traits": ["high agency", "comfort with ambiguity", "strong written communication", "user empathy", "systems thinking"],
            "red_flags_for_candidates": [
                "Needs detailed specs before starting work",
                "Prefers clear hierarchical escalation paths",
                "Uncomfortable making decisions without explicit sign-off",
                "Dislikes rapid context switching",
                "Measures success by hours worked rather than outcomes"
            ],
            "culture_summary": "Matcha-Tech operates like an early-stage startup that has retained its scrappiness at scale. The team prizes ownership, speed, and user outcomes above all else. People who thrive here are self-directed, write well, and are energized—not stressed—by ambiguity."
        }

        existing_profile = await conn.fetchrow(
            "SELECT id FROM culture_profiles WHERE company_id = $1", company_id
        )
        if existing_profile:
            await conn.execute(
                "UPDATE culture_profiles SET profile_data = $1, last_updated = NOW() WHERE company_id = $2",
                json.dumps(matcha_tech_culture_profile), company_id
            )
            print("Updated existing culture profile.")
        else:
            await conn.execute(
                "INSERT INTO culture_profiles (company_id, profile_data) VALUES ($1, $2)",
                company_id, json.dumps(matcha_tech_culture_profile)
            )
            print("Created culture profile.")

        # 4. Seed Candidate Records + Linked Interviews (Potential Matches)
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
                "culture_score": 89,
                "culture_reasoning": "Strong alignment with Matcha-Tech's core values. Alice's track record of ownership in high-velocity teams maps directly to the company's bias-for-action culture. Her explicit dislike of bureaucracy and comfort with ambiguity are textbook fits.",
                "culture_fit_breakdown": {
                    "collaboration_fit": {"score": 88, "reasoning": "Thrives in autonomous, self-organizing teams"},
                    "pace_fit": {"score": 94, "reasoning": "Has shipped in rapid-release environments before"},
                    "values_alignment": {"score": 91, "reasoning": "Ownership and user-centricity are her stated priorities"},
                    "growth_fit": {"score": 85, "reasoning": "Self-directed learner, aligns with internal mobility culture"},
                    "work_style_fit": {"score": 87, "reasoning": "Async-first communicator, strong written output"},
                },
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
                "culture_score": 76,
                "culture_reasoning": "Solid alignment on user-centricity and transparency. Bob's slight preference for structured process introduces some friction, but his expressed willingness to adapt and strong product instincts keep him firmly in-range.",
                "culture_fit_breakdown": {
                    "collaboration_fit": {"score": 80, "reasoning": "Works well cross-functionally, prefers defined roles"},
                    "pace_fit": {"score": 72, "reasoning": "Comfortable with agile but prefers sprint structure over continuous flow"},
                    "values_alignment": {"score": 82, "reasoning": "User empathy is genuine; ownership slightly conditional"},
                    "growth_fit": {"score": 75, "reasoning": "Grows well with mentorship, less self-directed than ideal"},
                    "work_style_fit": {"score": 71, "reasoning": "Good communicator but tends toward synchronous meetings"},
                },
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
                "culture_score": 48,
                "culture_reasoning": "Significant misalignment on pace and hierarchy. Charlie's explicit preference for structured environments and long planning cycles is the inverse of Matcha-Tech's decentralized, fast-iteration culture. Technical depth is a plus but unlikely to offset culture friction.",
                "culture_fit_breakdown": {
                    "collaboration_fit": {"score": 55, "reasoning": "Prefers hierarchical decision-making over flat self-organization"},
                    "pace_fit": {"score": 38, "reasoning": "Explicitly requested slower planning cycles"},
                    "values_alignment": {"score": 50, "reasoning": "Values process stability over bias for action"},
                    "growth_fit": {"score": 58, "reasoning": "Growth mindset present but tied to formal structure"},
                    "work_style_fit": {"score": 39, "reasoning": "Synchronous, meeting-heavy style conflicts with async-first norm"},
                },
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
                "culture_score": 28,
                "culture_reasoning": "Near-total misalignment. David's stated preference for rigid structure, dislike of ambiguity, and waterfall background are directly opposed to Matcha-Tech's operating model. This would be a difficult placement regardless of technical skill.",
                "culture_fit_breakdown": {
                    "collaboration_fit": {"score": 30, "reasoning": "Expects top-down decision flows, resists self-organization"},
                    "pace_fit": {"score": 22, "reasoning": "Waterfall mindset; rapid iteration is a stated stressor"},
                    "values_alignment": {"score": 28, "reasoning": "Values predictability over ownership and speed"},
                    "growth_fit": {"score": 35, "reasoning": "Career growth tied to title progression, not impact"},
                    "work_style_fit": {"score": 25, "reasoning": "Requires detailed specs, blocked by ambiguity"},
                },
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
                "culture_score": 94,
                "culture_reasoning": "Exceptional alignment. Eve's founder background makes her native to Matcha-Tech's operating culture — she has lived the fast iteration, radical ownership, and flat hierarchy. Her deep user focus and comfort with chaos are exactly what the team prizes.",
                "culture_fit_breakdown": {
                    "collaboration_fit": {"score": 93, "reasoning": "Built and led cross-functional teams without formal process"},
                    "pace_fit": {"score": 96, "reasoning": "Startup founder — rapid iteration is her baseline, not a stretch"},
                    "values_alignment": {"score": 95, "reasoning": "Ownership, user-centricity, and transparency are lived values"},
                    "growth_fit": {"score": 92, "reasoning": "Self-directed; creates her own growth opportunities"},
                    "work_style_fit": {"score": 94, "reasoning": "Async-first, high agency, thrives on ownership without hand-holding"},
                },
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

            # Upsert match_results so ranking run skips Gemini entirely
            await conn.execute("""
                INSERT INTO match_results (
                    company_id, candidate_id, match_score, match_reasoning, culture_fit_breakdown
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (company_id, candidate_id)
                DO UPDATE SET
                    match_score = $3,
                    match_reasoning = $4,
                    culture_fit_breakdown = $5,
                    created_at = NOW()
            """,
                company_id,
                candidate_id,
                cand["culture_score"],
                cand["culture_reasoning"],
                json.dumps(cand["culture_fit_breakdown"]),
            )

        print("\nSeed complete! Matcha-Tech is ready for multi-signal ranking.")
        print(f"Company ID: {company_id}")
        print("Run POST /companies/{company_id}/rankings/run to generate rankings.")

    await close_pool()

if __name__ == '__main__':
    asyncio.run(seed_matcha_tech())
