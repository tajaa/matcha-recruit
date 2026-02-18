"""
Celery task for project close workflow.

When a project closes (manually or by deadline):
1. Analyze any remaining unanalyzed screening interviews
2. Run ranking across all candidates with screening scores
3. Identify top 3 candidates by rank
4. Send admin interview invitation emails to top 3
5. Promote top 3 to 'finalist' stage
6. Mark project as 'completed'

Also provides a periodic task (check_project_deadlines) that auto-closes
projects past their closing_date.
"""

import asyncio
import json
from typing import Optional
from uuid import UUID

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


async def _close_project(project_id: str) -> dict:
    """Execute the full project close workflow."""
    from app.config import load_settings
    from app.workers.tasks.interview_analysis import _analyze_interview

    settings = load_settings()

    conn = await get_db_connection()
    try:
        # Get project details
        project = await conn.fetchrow(
            """
            SELECT id, company_name, name, position_title, company_id
            FROM projects WHERE id = $1
            """,
            project_id,
        )
        if not project:
            return {"error": "Project not found", "project_id": project_id}

        # Step 1: Find screening interviews linked to this project that aren't completed
        unanalyzed = await conn.fetch(
            """
            SELECT i.id, i.transcript
            FROM interviews i
            JOIN project_outreach po ON po.interview_id = i.id
            WHERE po.project_id = $1
              AND i.status != 'completed'
              AND i.transcript IS NOT NULL
              AND i.transcript != ''
            """,
            project_id,
        )

        # Analyze unanalyzed interviews directly (we're already in asyncio.run context)
        analyzed_count = 0
        for interview in unanalyzed:
            try:
                await _analyze_interview(
                    interview_id=str(interview["id"]),
                    interview_type="screening",
                    transcript=interview["transcript"],
                )
                analyzed_count += 1
                print(f"[ProjectClose] Analyzed stragglers interview {interview['id']}")
            except Exception as e:
                print(f"[ProjectClose] Failed to analyze interview {interview['id']}: {e}")

        # Step 2: Get all non-rejected candidates in this project
        candidate_rows = await conn.fetch(
            """
            SELECT candidate_id FROM project_candidates
            WHERE project_id = $1 AND stage NOT IN ('rejected')
            """,
            project_id,
        )
        candidate_ids = [row["candidate_id"] for row in candidate_rows]

        top_3_candidates = []
        company_id = project["company_id"]

        # Step 3: Try multi-signal ranking if company has a culture profile
        if company_id and candidate_ids:
            try:
                from app.matcha.services.ranking_service import RankingService

                ranking_service = RankingService(
                    api_key=settings.gemini_api_key,
                    vertex_project=settings.vertex_project,
                    vertex_location=settings.vertex_location or "us-central1",
                    model=settings.analysis_model,
                )
                results = await ranking_service.run_ranking(company_id, candidate_ids)
                top_3_candidates = [
                    {"candidate_id": r["candidate_id"]}
                    for r in results[:3]
                ]
                print(f"[ProjectClose] Ranking complete. Top {len(top_3_candidates)} candidates identified.")
            except ValueError:
                print("[ProjectClose] No culture profile for company — falling back to screening score ranking.")
            except Exception as e:
                print(f"[ProjectClose] Ranking failed: {e} — falling back to screening score ranking.")

        # Step 4: Fallback — rank by screening score if ranking failed or no company_id.
        # Exclude candidates already rejected in the pipeline.
        if not top_3_candidates:
            fallback_rows = await conn.fetch(
                """
                SELECT DISTINCT po.candidate_id, po.screening_score
                FROM project_outreach po
                JOIN project_candidates pc
                  ON pc.project_id = po.project_id AND pc.candidate_id = po.candidate_id
                WHERE po.project_id = $1
                  AND po.screening_score IS NOT NULL
                  AND pc.stage != 'rejected'
                ORDER BY po.screening_score DESC
                LIMIT 3
                """,
                project_id,
            )
            top_3_candidates = [{"candidate_id": row["candidate_id"]} for row in fallback_rows]
            print(f"[ProjectClose] Fallback: {len(top_3_candidates)} candidates by screening score.")

        # Step 5: Send admin interview invitation emails to top 3
        from app.core.services.email import get_email_service

        email_service = get_email_service()
        position_title = project["position_title"] or project["name"]
        emails_sent = []

        for entry in top_3_candidates:
            cand_id = entry["candidate_id"]
            candidate = await conn.fetchrow(
                "SELECT name, email FROM candidates WHERE id = $1",
                cand_id,
            )
            if not candidate or not candidate["email"]:
                continue

            # Promote to finalist stage
            await conn.execute(
                """
                UPDATE project_candidates
                SET stage = 'finalist', updated_at = NOW()
                WHERE project_id = $1 AND candidate_id = $2
                """,
                project_id,
                cand_id,
            )

            # Send email
            success = await email_service.send_admin_interview_invitation_email(
                candidate_email=candidate["email"],
                candidate_name=candidate["name"],
                company_name=project["company_name"],
                position_title=position_title,
            )

            if success:
                emails_sent.append(str(cand_id))
                print(f"[ProjectClose] Admin interview invitation sent to {candidate['email']}")
            else:
                print(f"[ProjectClose] Failed to send invitation to {candidate['email']}")

        # Step 6: Mark project as completed
        await conn.execute(
            "UPDATE projects SET status = 'completed', updated_at = NOW() WHERE id = $1",
            project_id,
        )

        return {
            "project_id": project_id,
            "analyzed_interviews": analyzed_count,
            "top_candidates": emails_sent,
            "emails_sent": len(emails_sent),
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=2)
def close_project_async(self, project_id: str):
    """
    Execute the project close workflow in the background.

    Triggered manually via the admin UI or automatically by check_project_deadlines.
    """
    print(f"[ProjectClose] Starting close workflow for project {project_id}")

    try:
        result = asyncio.run(_close_project(project_id))

        publish_task_complete(
            channel=f"project:{project_id}",
            task_type="project_close",
            entity_id=project_id,
            result=result,
        )

        print(f"[ProjectClose] Completed close workflow for project {project_id}: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[ProjectClose] Failed close workflow for project {project_id}: {e}")

        publish_task_error(
            channel=f"project:{project_id}",
            task_type="project_close",
            entity_id=project_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=120)


@celery_app.task
def check_project_deadlines():
    """
    Daily scheduled task: find projects past their closing_date and trigger close workflow.

    Enabled/disabled via scheduler_settings table (task_key = 'project_deadline_checks').
    """
    async def _check():
        conn = await get_db_connection()
        try:
            overdue = await conn.fetch(
                """
                SELECT id FROM projects
                WHERE closing_date IS NOT NULL
                  AND closing_date < NOW()
                  AND status IN ('active', 'closing')
                """
            )
            for row in overdue:
                close_project_async.delay(str(row["id"]))
                print(f"[ProjectDeadlines] Queued close for overdue project {row['id']}")
            return {"queued": len(overdue)}
        finally:
            await conn.close()

    result = asyncio.run(_check())
    print(f"[ProjectDeadlines] Deadline check complete: {result}")
    return result
