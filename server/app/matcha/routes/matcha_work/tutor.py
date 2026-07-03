"""Language tutor voice sessions (Gemini Live): start/status/check the
per-utterance grammar-check pass, plus the EN/ES/FR prompt templates.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.services import matcha_work_document as doc_svc

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/threads/{thread_id}/tutor/start")
async def start_tutor_voice_session(
    thread_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Start a Gemini Live language tutor voice session linked to a matcha-work thread."""
    from app.core.services.auth import create_interview_ws_token

    language = body.get("language", "en")
    if language not in ("en", "es-mx", "fr"):
        raise HTTPException(status_code=400, detail="Language must be 'en', 'es-mx', or 'fr'")
    duration_minutes = body.get("duration_minutes", 5)
    if duration_minutes not in (0.33, 2, 5, 8):
        raise HTTPException(status_code=400, detail="Duration must be 0.33 (20s test), 2, 5, or 8 minutes")

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify thread exists and belongs to user
        thread = await conn.fetchrow(
            "SELECT id, current_state FROM mw_threads WHERE id = $1 AND company_id IS NOT DISTINCT FROM $2",
            thread_id, company_id,
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Create interview record (same as POST /tutor/sessions with mode=language_test)
        row = await conn.fetchrow(
            """
            INSERT INTO interviews (company_id, interviewer_name, interviewer_role, interview_type, status)
            VALUES (NULL, $1, $2, 'tutor_language', 'pending')
            RETURNING id
            """,
            current_user.email,
            language,
        )
        interview_id = row["id"]

        # Store interview_id in thread current_state
        raw_state = thread["current_state"]
        if isinstance(raw_state, str):
            current_state = json.loads(raw_state) if raw_state else {}
        elif isinstance(raw_state, dict):
            current_state = dict(raw_state)
        else:
            current_state = {}
        current_state["language_tutor"] = {
            "interview_id": str(interview_id),
            "language": language,
            "status": "active",
        }
        await conn.execute(
            "UPDATE mw_threads SET current_state = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(current_state), thread_id,
        )

    duration_seconds = int(duration_minutes * 60)
    return {
        "interview_id": str(interview_id),
        "websocket_url": f"/api/ws/interview/{interview_id}",
        "ws_auth_token": create_interview_ws_token(interview_id),
        "max_session_duration_seconds": duration_seconds,
    }

@router.get("/threads/{thread_id}/tutor/status")
async def get_tutor_voice_status(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Poll language tutor session status and analysis results.

    Runs analysis inline (no Celery) on first poll after session ends.
    """
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        thread = await conn.fetchrow(
            "SELECT id, current_state FROM mw_threads WHERE id = $1 AND company_id IS NOT DISTINCT FROM $2",
            thread_id, company_id,
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        raw_state = thread["current_state"]
        if isinstance(raw_state, str):
            current_state = json.loads(raw_state) if raw_state else {}
        elif isinstance(raw_state, dict):
            current_state = dict(raw_state)
        else:
            current_state = {}
        tutor_state = current_state.get("language_tutor")
        if not tutor_state or not tutor_state.get("interview_id"):
            raise HTTPException(status_code=404, detail="No tutor session found for this thread")

        interview_id = tutor_state["interview_id"]
        interview = await conn.fetchrow(
            "SELECT status, tutor_analysis, transcript FROM interviews WHERE id = $1",
            UUID(interview_id),
        )
        if not interview:
            raise HTTPException(status_code=404, detail="Interview record not found")

        tutor_analysis = interview["tutor_analysis"]
        interview_status = interview["status"]

        # Run analysis inline if session ended but analysis hasn't run yet.
        # Atomically claim the analysis slot to prevent duplicate runs from concurrent polls.
        if interview_status in ("analyzing", "completed") and not tutor_analysis and interview["transcript"]:
            claimed = await conn.fetchval(
                "UPDATE interviews SET status = 'analyzing_inline' WHERE id = $1 AND status IN ('analyzing', 'completed') AND tutor_analysis IS NULL RETURNING id",
                UUID(interview_id),
            )
            if not claimed:
                # Another request is already running analysis
                return {"status": "analyzing", "tutor_analysis": None}
            try:
                from app.matcha.services.conversation_analyzer import ConversationAnalyzer
                settings = get_settings()
                analyzer = ConversationAnalyzer(
                    api_key=settings.gemini_api_key,
                    model=settings.analysis_model,
                )
                language = tutor_state.get("language", "en")
                tutor_analysis = await analyzer.analyze_tutor_language(
                    transcript=interview["transcript"],
                    language=language,
                )
                # Save analysis and mark completed
                await conn.execute(
                    "UPDATE interviews SET tutor_analysis = $1, status = 'completed' WHERE id = $2",
                    json.dumps(tutor_analysis), UUID(interview_id),
                )
                interview_status = "completed"
            except Exception as e:
                logger.error("Inline tutor analysis failed: %s", e)
                # Reset status so next poll can retry
                await conn.execute(
                    "UPDATE interviews SET status = 'analyzing' WHERE id = $1",
                    UUID(interview_id),
                )
                return {"status": "analyzing", "tutor_analysis": None}

        result = {
            "status": interview_status,
            "tutor_analysis": tutor_analysis if isinstance(tutor_analysis, dict) else (json.loads(tutor_analysis) if tutor_analysis else None),
        }

        # When analysis is complete, save summary as assistant message (idempotent)
        if interview_status == "completed" and tutor_analysis and not tutor_state.get("message_saved"):
            analysis = tutor_analysis if isinstance(tutor_analysis, dict) else json.loads(tutor_analysis)
            proficiency = analysis.get("overall_proficiency", {})
            level = proficiency.get("level", "N/A")
            level_desc = proficiency.get("level_description", "")
            summary_text = f"**Language Practice Complete** — CEFR Level: **{level}** ({level_desc})\n\n"
            strengths = proficiency.get("strengths", [])
            if strengths:
                summary_text += "**Strengths:** " + ", ".join(strengths) + "\n\n"
            areas = proficiency.get("areas_to_improve", [])
            if areas:
                summary_text += "**Areas to Improve:** " + ", ".join(areas) + "\n\n"
            grammar_data = analysis.get("grammar", {})
            errors = grammar_data.get("common_errors", [])
            if errors:
                summary_text += "**Grammar Notes:**\n"
                for err in errors[:5]:
                    if isinstance(err, dict):
                        summary_text += f"- {err.get('error', '')}: {err.get('correction', '')}\n"
                    else:
                        summary_text += f"- {err}\n"

            await doc_svc.add_message(thread_id, "assistant", summary_text.strip())

            # Mark message as saved so we don't duplicate
            current_state_updated = dict(current_state)
            current_state_updated["language_tutor"]["message_saved"] = True
            current_state_updated["language_tutor"]["status"] = "completed"
            await conn.execute(
                "UPDATE mw_threads SET current_state = $1, updated_at = NOW() WHERE id = $2",
                json.dumps(current_state_updated), thread_id,
            )

        return result

UTTERANCE_CHECK_PROMPT_EN = """You are a language tutor analyzing a student's English utterance for errors.

Utterance: "{utterance}"

Return a JSON array of errors found. Each error object has:
- "error": the incorrect word/phrase exactly as spoken
- "correction": the correct form
- "type": one of "grammar", "vocabulary", "pronunciation"
- "brief": a 5-word max explanation

If no errors, return an empty array [].
Only flag clear mistakes, not stylistic preferences. Be concise.
Return ONLY valid JSON, no markdown."""

UTTERANCE_CHECK_PROMPT_ES = """Eres un tutor de idiomas analizando una frase en español de un estudiante.

Frase: "{utterance}"

Devuelve un array JSON de errores encontrados. Cada objeto tiene:
- "error": la palabra/frase incorrecta exactamente como fue dicha
- "correction": la forma correcta
- "type": uno de "grammar", "vocabulary", "pronunciation"
- "brief": explicación de máximo 5 palabras

Si no hay errores, devuelve un array vacío [].
Solo marca errores claros, no preferencias de estilo. Sé conciso.
Devuelve SOLO JSON válido, sin markdown."""

UTTERANCE_CHECK_PROMPT_FR = """Tu es un tuteur de langues analysant une phrase en français d'un étudiant.

Phrase: "{utterance}"

Renvoie un tableau JSON des erreurs trouvées. Chaque objet contient:
- "error": le mot/la phrase incorrecte exactement comme prononcé
- "correction": la forme correcte
- "type": l'un de "grammar", "vocabulary", "pronunciation"
- "brief": explication de 5 mots maximum

S'il n'y a pas d'erreurs, renvoie un tableau vide [].
Ne signale que les erreurs claires, pas les préférences stylistiques. Sois concis.
Renvoie UNIQUEMENT du JSON valide, pas de markdown."""

@router.post("/threads/{thread_id}/tutor/check")
async def check_tutor_utterance(
    thread_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Real-time error check on a single user utterance during a voice session."""
    utterance = (body.get("utterance") or "").strip()
    language = body.get("language", "en")

    if not utterance or len(utterance) < 3:
        return {"errors": []}

    settings = get_settings()
    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)

        if language in ("es", "es-mx"):
            prompt = UTTERANCE_CHECK_PROMPT_ES.format(utterance=utterance)
        elif language == "fr":
            prompt = UTTERANCE_CHECK_PROMPT_FR.format(utterance=utterance)
        else:
            prompt = UTTERANCE_CHECK_PROMPT_EN.format(utterance=utterance)
        response = await client.aio.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        errors = json.loads(text)
        return {"errors": errors if isinstance(errors, list) else []}
    except Exception as e:
        logger.warning("Utterance check failed: %s", e)
        return {"errors": []}
