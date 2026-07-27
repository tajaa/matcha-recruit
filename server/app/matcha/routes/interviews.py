from typing import Optional
from uuid import UUID
import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query

from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser

from ...database import get_connection
from ..models.interview import InterviewCreate, InterviewResponse, InterviewStart
from ...core.services.gemini_session import GeminiLiveSession
from ...core.services.auth import (
    create_interview_ws_token,
    decode_interview_ws_token,
    decode_token,
)
from ..services.interviews.culture_analyzer import CultureAnalyzer
from ..services.interviews.conversation_analyzer import ConversationAnalyzer
from ...protocol import (
    MessageType,
    parse_text_message,
    parse_audio_from_client,
    frame_audio_for_client,
    ConversationMessage,
)
from ...config import get_settings

router = APIRouter()


@router.post("/companies/{company_id}/interviews", response_model=InterviewStart)
async def create_interview(
    company_id: UUID,
    interview: InterviewCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new interview session for a company."""
    if current_user.role == "client":
        owned = await get_client_company_id(current_user)
        if owned != company_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    async with get_connection() as conn:
        # Verify company exists
        company = await conn.fetchrow(
            "SELECT id FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Flow enforcement: candidate (culture-fit) interviews require culture profile
        if interview.interview_type == "candidate":
            culture_profile = await conn.fetchrow(
                "SELECT id FROM culture_profiles WHERE company_id = $1",
                company_id,
            )
            if not culture_profile:
                raise HTTPException(
                    status_code=400,
                    detail="Culture interview must be completed first. Complete at least one culture interview and aggregate the culture profile before running candidate interviews."
                )

        # Create interview record
        row = await conn.fetchrow(
            """
            INSERT INTO interviews (company_id, interviewer_name, interviewer_role, interview_type, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING id
            """,
            company_id,
            interview.interviewer_name,
            interview.interviewer_role,
            interview.interview_type,
        )
        interview_id = row["id"]

        return InterviewStart(
            interview_id=interview_id,
            websocket_url=f"/api/ws/interview/{interview_id}",
            ws_auth_token=create_interview_ws_token(interview_id),
        )


@router.get("/interviews/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get an interview by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, interviewer_name, interviewer_role, interview_type,
                   transcript, raw_culture_data, conversation_analysis, screening_analysis,
                   tutor_analysis, status, created_at, completed_at
            FROM interviews
            WHERE id = $1
            """,
            interview_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Interview not found")

        # Tenant isolation: transcripts/analysis are confidential. Clients may
        # only read interviews belonging to their own company (404, not 403, to
        # avoid leaking existence).
        if current_user.role != "admin":
            owned = await get_client_company_id(current_user)
            if str(row["company_id"]) != str(owned):
                raise HTTPException(status_code=404, detail="Interview not found")

        raw_culture_data = None
        if row["raw_culture_data"]:
            raw_culture_data = json.loads(row["raw_culture_data"]) if isinstance(row["raw_culture_data"], str) else row["raw_culture_data"]

        conversation_analysis = None
        if row["conversation_analysis"]:
            conversation_analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]

        screening_analysis = None
        if row["screening_analysis"]:
            screening_analysis = json.loads(row["screening_analysis"]) if isinstance(row["screening_analysis"], str) else row["screening_analysis"]

        tutor_analysis = None
        if row["tutor_analysis"]:
            tutor_analysis = json.loads(row["tutor_analysis"]) if isinstance(row["tutor_analysis"], str) else row["tutor_analysis"]

        return InterviewResponse(
            id=row["id"],
            company_id=row["company_id"],
            interviewer_name=row["interviewer_name"],
            interviewer_role=row["interviewer_role"],
            interview_type=row["interview_type"] or "culture",
            transcript=row["transcript"],
            raw_culture_data=raw_culture_data,
            conversation_analysis=conversation_analysis,
            screening_analysis=screening_analysis,
            tutor_analysis=tutor_analysis,
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )


@router.get("/companies/{company_id}/interviews", response_model=list[InterviewResponse])
async def list_company_interviews(
    company_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all interviews for a company."""
    # Tenant isolation: a client may only list its own company's interviews.
    if current_user.role != "admin":
        owned = await get_client_company_id(current_user)
        if str(company_id) != str(owned):
            raise HTTPException(status_code=404, detail="Company not found")
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, company_id, interviewer_name, interviewer_role, interview_type,
                   transcript, raw_culture_data, conversation_analysis, screening_analysis,
                   status, created_at, completed_at
            FROM interviews
            WHERE company_id = $1
            ORDER BY created_at DESC
            """,
            company_id,
        )
        results = []
        for row in rows:
            raw_culture_data = None
            if row["raw_culture_data"]:
                raw_culture_data = json.loads(row["raw_culture_data"]) if isinstance(row["raw_culture_data"], str) else row["raw_culture_data"]
            conversation_analysis = None
            if row["conversation_analysis"]:
                conversation_analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]
            screening_analysis = None
            if row["screening_analysis"]:
                screening_analysis = json.loads(row["screening_analysis"]) if isinstance(row["screening_analysis"], str) else row["screening_analysis"]
            results.append(InterviewResponse(
                id=row["id"],
                company_id=row["company_id"],
                interviewer_name=row["interviewer_name"],
                interviewer_role=row["interviewer_role"],
                interview_type=row["interview_type"] or "culture",
                transcript=row["transcript"],
                raw_culture_data=raw_culture_data,
                conversation_analysis=conversation_analysis,
                screening_analysis=screening_analysis,
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            ))
        return results


@router.get("/interviews/{interview_id}/analysis")
async def get_interview_analysis(
    interview_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get the conversation analysis for an interview."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT company_id, conversation_analysis
            FROM interviews
            WHERE id = $1
            """,
            interview_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Interview not found")

        # Tenant isolation: clients may only read their own company's analysis.
        if current_user.role != "admin":
            owned = await get_client_company_id(current_user)
            if str(row["company_id"]) != str(owned):
                raise HTTPException(status_code=404, detail="Interview not found")

        if not row["conversation_analysis"]:
            raise HTTPException(status_code=404, detail="Analysis not yet generated for this interview")

        analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]
        return analysis


@router.post("/interviews/{interview_id}/analyze")
async def analyze_interview(
    interview_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate or regenerate conversation analysis for an interview."""
    settings = get_settings()

    async with get_connection() as conn:
        # Fetch interview
        row = await conn.fetchrow(
            """
            SELECT id, company_id, interview_type, transcript, status
            FROM interviews
            WHERE id = $1
            """,
            interview_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Interview not found")

        if current_user.role == "client":
            owned = await get_client_company_id(current_user)
            if owned != row["company_id"]:
                raise HTTPException(status_code=403, detail="Forbidden")

        if row["status"] != "completed":
            raise HTTPException(status_code=400, detail="Interview must be completed before analysis")

        if not row["transcript"]:
            raise HTTPException(status_code=400, detail="Interview has no transcript to analyze")

        # Run analysis
        conv_analyzer = ConversationAnalyzer(
            api_key=settings.gemini_api_key,
            model=settings.analysis_model,
        )

        interview_type = row["interview_type"] or "culture"

        if interview_type == "screening":
            # Screening interviews use a different analysis method
            analysis = await conv_analyzer.analyze_screening_interview(
                transcript=row["transcript"],
            )
            # Store in screening_analysis column
            await conn.execute(
                """
                UPDATE interviews
                SET screening_analysis = $1
                WHERE id = $2
                """,
                json.dumps(analysis),
                interview_id,
            )
        else:
            # Culture and candidate interviews use conversation analysis
            culture_profile = None
            if interview_type == "candidate":
                culture_row = await conn.fetchrow(
                    "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
                    row["company_id"],
                )
                if culture_row and culture_row["profile_data"]:
                    culture_profile = json.loads(culture_row["profile_data"]) if isinstance(culture_row["profile_data"], str) else culture_row["profile_data"]

            analysis = await conv_analyzer.analyze_interview(
                transcript=row["transcript"],
                interview_type=interview_type,
                culture_profile=culture_profile,
            )
            # Store in conversation_analysis column
            await conn.execute(
                """
                UPDATE interviews
                SET conversation_analysis = $1
                WHERE id = $2
                """,
                json.dumps(analysis),
                interview_id,
            )

        return analysis


def _token_from_request(
    websocket: WebSocket, query_token: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Extract the JWT from the handshake. Sources, in preference order:

    1. ``Sec-WebSocket-Protocol: bearer, <token>`` — web clients; keeps the token
       out of the URL so it never lands in nginx/proxy access logs.
    2. ``?token=`` query param — legacy web clients / pre-deploy tabs.
    3. ``Authorization: Bearer`` header — native clients.

    Returns ``(token, subprotocol_to_echo)`` — when the token arrived via subprotocol
    the accept() MUST echo ``"bearer"`` or browsers fail the handshake. (Mirrors the
    same helper in work/thread_ws.py, work/project_ws.py, werk/channels_ws.py.)
    """
    proto = websocket.headers.get("sec-websocket-protocol")
    if proto:
        parts = [p.strip() for p in proto.split(",")]
        if len(parts) >= 2 and parts[0] == "bearer" and parts[1]:
            return parts[1], "bearer"
    if query_token:
        return query_token, None
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:], None
    return None, None


# WebSocket endpoint for voice interviews
@router.websocket("/ws/interview/{interview_id}")
async def interview_websocket(
    websocket: WebSocket,
    interview_id: UUID,
    token: Optional[str] = Query(None),
):
    """WebSocket endpoint for voice interview sessions."""
    # Prefer the token from the `bearer` subprotocol (keeps it out of access logs);
    # fall back to the legacy `?token=` query param for pre-deploy tabs.
    token, subprotocol = _token_from_request(websocket, token)
    await websocket.accept(subprotocol=subprotocol)
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    settings = get_settings()
    cancelled = False
    gemini_session: Optional[GeminiLiveSession] = None
    analyzer = CultureAnalyzer(
        api_key=settings.gemini_api_key,
        model=settings.analysis_model,
    )

    # Get interview and company info
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.id, i.company_id, i.interviewer_name, i.interviewer_role,
                   i.interview_type, i.raw_culture_data, c.name as company_name
            FROM interviews i
            LEFT JOIN companies c ON i.company_id = c.id
            WHERE i.id = $1
            """,
            interview_id,
        )
        if not row:
            await websocket.close(code=4004, reason="Interview not found")
            return

        interview_type = row["interview_type"] or "culture"

        # Allow either:
        # 1) short-lived interview websocket token (for public invite flows), or
        # 2) authenticated app access token (for internal flows).
        ws_token_interview_id, is_practice = decode_interview_ws_token(token)
        if ws_token_interview_id:
            if ws_token_interview_id != interview_id:
                await websocket.close(code=4003, reason="Token not valid for this interview")
                return
        else:
            is_practice = False
            user_payload = decode_token(token)
            if not user_payload:
                await websocket.close(code=4001, reason="Invalid or expired token")
                return

            try:
                user_id = UUID(user_payload.sub)
            except ValueError:
                await websocket.close(code=4001, reason="Invalid token subject")
                return

            user_row = await conn.fetchrow(
                """
                SELECT id, email, role, is_active
                FROM users
                WHERE id = $1
                """,
                user_id,
            )
            if not user_row or not user_row["is_active"]:
                await websocket.close(code=4001, reason="Invalid or inactive user")
                return

            # Tutor sessions are private to their owner (or admin).
            if interview_type in ("tutor_interview", "tutor_language") and user_row["role"] != "admin":
                owner_email = (row["interviewer_name"] or "").strip().lower()
                if owner_email != (user_row["email"] or "").strip().lower():
                    await websocket.close(code=4003, reason="Not authorized for this tutor session")
                    return

        company_name = row["company_name"] or "Practice Session"
        interviewer_name = row["interviewer_name"] or "HR Representative"
        interviewer_role = row["interviewer_role"]  # May contain language for tutor sessions

        # For tutor sessions, extract the appropriate fields
        tutor_language = None
        tutor_interview_role = None
        if interview_type == "tutor_language":
            tutor_language = interviewer_role  # "en" or "es"
            interviewer_role = "Tutor"
        elif interview_type == "tutor_interview":
            tutor_interview_role = interviewer_role  # The role being practiced for

        # For screening/candidate interviews, pull the candidate's name and
        # position title so they can be injected into the Gemini system prompt.
        # Without this the model has no textual reference for the name and
        # will hallucinate (e.g. "Mark" → "Marcia") when relying on voice
        # transcription alone.
        candidate_name_for_prompt: Optional[str] = None
        position_title_for_prompt: Optional[str] = None
        if interview_type in ("screening", "candidate"):
            raw = row["raw_culture_data"]
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = {}
            if isinstance(raw, dict):
                candidate_name_for_prompt = raw.get("candidate_name")
                position_title_for_prompt = raw.get("position_title")
            if not candidate_name_for_prompt:
                # For screening rows the candidate name is also stored in
                # interviews.interviewer_name (see matcha_work.py create flow).
                candidate_name_for_prompt = row["interviewer_name"]

        # For candidate interviews, fetch the company's culture profile
        culture_profile = None
        if interview_type == "candidate" and row["company_id"]:
            culture_row = await conn.fetchrow(
                "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
                row["company_id"],
            )
            if culture_row and culture_row["profile_data"]:
                culture_profile = json.loads(culture_row["profile_data"]) if isinstance(culture_row["profile_data"], str) else culture_row["profile_data"]

        # For investigation interviews, fetch incident data and generated questions
        incident_summary = None
        investigation_questions_text = None
        interviewee_name_for_prompt = None
        interviewee_role_for_prompt = None
        incident_id_str = None
        if interview_type == "investigation":
            inv_row = await conn.fetchrow(
                """
                SELECT irii.interviewee_name, irii.interviewee_role, irii.questions_generated,
                       ir.title, ir.description, ir.incident_type, ir.severity, ir.location, ir.occurred_at,
                       ir.id as incident_id
                FROM ir_investigation_interviews irii
                JOIN ir_incidents ir ON irii.incident_id = ir.id
                WHERE irii.interview_id = $1
                """,
                interview_id,
            )
            if inv_row:
                incident_id_str = str(inv_row["incident_id"])
                interviewee_name_for_prompt = inv_row["interviewee_name"]
                interviewee_role_for_prompt = inv_row["interviewee_role"]
                incident_summary = (
                    f"Title: {inv_row['title']}\n"
                    f"Type: {inv_row['incident_type']}\n"
                    f"Severity: {inv_row['severity']}\n"
                    f"Description: {inv_row['description'] or 'N/A'}\n"
                    f"Location: {inv_row['location'] or 'N/A'}\n"
                    f"Occurred: {inv_row['occurred_at'] or 'N/A'}"
                )
                questions = inv_row["questions_generated"]
                if isinstance(questions, str):
                    questions = json.loads(questions)
                if questions:
                    investigation_questions_text = "\n".join(
                        f"{i+1}. [{q.get('category', 'general')}] {q.get('question', '')}"
                        for i, q in enumerate(questions)
                        if q.get('question')
                    )
                # Update junction table status
                await conn.execute(
                    "UPDATE ir_investigation_interviews SET status = 'in_progress' WHERE interview_id = $1",
                    interview_id,
                )

        # Update interview status
        await conn.execute(
            "UPDATE interviews SET status = 'in_progress' WHERE id = $1",
            interview_id,
        )

    async def send_message(msg_type: str, content: str):
        msg = ConversationMessage.create(msg_type, content)
        await websocket.send_text(msg.to_json())

    await send_message(MessageType.SYSTEM, f"Connected to interview for {company_name}")

    try:
        # Screening + candidate interviews (the recruiting-project flow) get the
        # human-fluidity Live API features: affective dialog (model adapts to
        # emotional tone) and proactive audio (model holds back when the user
        # is mumbling, thinking aloud, or there's background noise).
        # These features are documented as v1alpha — route through the alpha
        # endpoint when they're on, so the server doesn't silently drop them.
        wants_human_features = interview_type in ("screening", "candidate")

        # Create Gemini session.
        # Use Google AI API (not Vertex) for live sessions — 3.1 models
        # only available on Google AI, and 2.5 is being discontinued on Vertex.
        gemini_session = GeminiLiveSession(
            model=settings.live_model,
            voice=settings.voice,
            api_key=settings.gemini_api_key,
            use_alpha_api=wants_human_features,
        )

        # Connect with appropriate interview prompt + new Live API features.
        # Gemini Live occasionally throws transient 1011 INTERNAL on connect;
        # retry once with short backoff before bubbling to the user.
        connect_kwargs = dict(
            company_name=company_name,
            interviewer_name=interviewer_name,
            interviewer_role=interviewer_role or "HR",
            interview_type=interview_type,
            culture_profile=culture_profile,
            tutor_language=tutor_language,
            tutor_interview_role=tutor_interview_role,
            incident_summary=incident_summary,
            investigation_questions=investigation_questions_text,
            interviewee_name_for_prompt=interviewee_name_for_prompt,
            interviewee_role_for_prompt=interviewee_role_for_prompt,
            candidate_name=candidate_name_for_prompt,
            position_title=position_title_for_prompt,
            no_interruption=(interview_type == "investigation"),
            enable_affective_dialog=wants_human_features,
            enable_proactive_audio=wants_human_features,
        )
        last_connect_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                await gemini_session.connect(**connect_kwargs)
                last_connect_error = None
                break
            except Exception as e:
                last_connect_error = e
                msg = str(e)
                is_transient = (
                    "1011" in msg
                    or "Internal error encountered" in msg
                    or "INTERNAL" in msg.upper()
                    or e.__class__.__name__ == "ServerError"
                )
                if not is_transient or attempt == 1:
                    raise
                print(f"[Interview {interview_id}] Gemini transient error on connect (attempt {attempt + 1}): {e}; retrying")
                try:
                    await gemini_session.close()
                except Exception:
                    pass
                gemini_session = GeminiLiveSession(
                    model=settings.live_model,
                    voice=settings.voice,
                    api_key=settings.gemini_api_key,
                    use_alpha_api=wants_human_features,
                )
                await asyncio.sleep(0.75)

        await send_message(MessageType.STATUS, "Session started")

        # Trigger the model to speak first
        if interview_type == "investigation":
            name = interviewee_name_for_prompt or "the interviewee"
            await gemini_session.send_text(f"Please begin the investigation interview now. Introduce yourself to {name}, explain this is a fact-finding conversation, and start with the introduction protocol.")
        elif interview_type == "tutor_interview":
            role_msg = f" for a {tutor_interview_role} position" if tutor_interview_role else ""
            await gemini_session.send_text(f"Please start the coaching session now. Greet them warmly and explain you'll help them practice interview questions{role_msg}.")
        elif interview_type == "tutor_language":
            if tutor_language == "es":
                await gemini_session.send_text("Por favor, comienza la sesión de práctica. Saluda calurosamente y pregunta cómo pueden ayudarte a practicar español hoy.")
            else:
                await gemini_session.send_text("Please start the practice session now. Greet them warmly and ask how you can help them practice English today.")
        elif interview_type in ("candidate", "screening"):
            name = candidate_name_for_prompt or "the candidate"
            await gemini_session.send_text(
                f"Please start the interview now. Greet {name} by name warmly in your very first sentence, then begin."
            )
        else:
            await gemini_session.send_text(f"Please start the interview now. Say hello to {interviewer_name} and begin.")

        # Start response forwarding task
        import asyncio

        async def forward_responses():
            async for response in gemini_session.receive_responses():
                if response.type == "audio" and response.audio_data:
                    await websocket.send_bytes(frame_audio_for_client(response.audio_data))
                elif response.type == "transcription":
                    if response.is_input_transcription:
                        await send_message(MessageType.USER, response.text)
                    else:
                        await send_message(MessageType.ASSISTANT, response.text)
                elif response.type == "interrupted":
                    # User barged in — tell client to stop playing queued audio
                    await send_message(MessageType.STATUS, "interrupted")
                elif response.type == "turn_complete":
                    await send_message(MessageType.STATUS, "ready")

        forward_task = asyncio.create_task(forward_responses())

        # Auto-stop timer for screening interviews — full 2-minute vetting interview.
        # Hard cap at 150s (2.5 min) gives the model headroom to wrap up gracefully
        # if a candidate is mid-answer when the wrap-up signal fires at 120s.
        session_timeout = None
        if interview_type == "screening":
            SCREENING_DURATION_SECONDS = 120

            async def auto_stop_session():
                await asyncio.sleep(SCREENING_DURATION_SECONDS)
                print(f"[Interview {interview_id}] Screening wrap-up signal after {SCREENING_DURATION_SECONDS}s")
                await send_message(MessageType.STATUS, "session_ending")
                # Tell the model to wrap up
                if gemini_session:
                    await gemini_session.send_text("Time is almost up. Please wrap up the interview now with a brief thank you and goodbye, keeping it to one or two sentences.")
                await asyncio.sleep(20)  # Give model time to finish current answer + say goodbye
                await send_message(MessageType.STATUS, "session_ended")

            session_timeout = asyncio.create_task(auto_stop_session())

        # Handle incoming messages
        audio_frame_count = 0
        timed_out = False
        while True:
            # Check if session timed out
            if session_timeout and session_timeout.done():
                timed_out = True
                break

            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if "text" in message:
                cmd = parse_text_message(message["text"])
                if cmd and cmd.command == "cancel_session":
                    cancelled = True
                    break
                elif cmd and cmd.command == "stop_session":
                    # For tutor sessions, stop = cancel (no analysis needed)
                    if interview_type in ("tutor_language", "tutor_interview"):
                        cancelled = True
                    break
                elif cmd and cmd.command == "send_text":
                    # Allow sending text messages (for testing)
                    if hasattr(cmd, "text") and cmd.text:
                        await gemini_session.send_text(cmd.text)

            elif "bytes" in message:
                audio_data = parse_audio_from_client(message["bytes"])
                if audio_data:
                    audio_frame_count += 1
                    if audio_frame_count % 50 == 0:
                        print(f"[Interview {interview_id}] Audio frame #{audio_frame_count}: {len(audio_data)} bytes")
                    await gemini_session.send_audio(audio_data)

        if session_timeout and not session_timeout.done():
            session_timeout.cancel()

    except WebSocketDisconnect:
        print(f"[Interview {interview_id}] Client disconnected")
    except RuntimeError as e:
        if "disconnect" in str(e).lower() or "receive" in str(e).lower():
            print(f"[Interview {interview_id}] Client disconnected (RuntimeError)")
        else:
            print(f"[Interview {interview_id}] RuntimeError: {e}")
            try:
                await send_message(MessageType.SYSTEM, f"Error: {str(e)}")
            except Exception:
                pass
    except Exception as e:
        import traceback
        error_type = e.__class__.__name__
        error_msg = str(e)
        print(f"[Interview {interview_id}] Error ({error_type}): {error_msg}\n{traceback.format_exc()}")
        
        # Format a user-friendly error message
        friendly_error = "An unexpected error occurred connecting to the AI."
        if "RateLimitExceeded" in error_type or "429" in error_msg or "quota" in error_msg.lower():
            friendly_error = "The AI system is currently at capacity. Please try again in a few minutes."
        elif "403" in error_msg or "permission" in error_msg.lower() or "api key" in error_msg.lower():
            friendly_error = "AI service configuration error. Please contact support."
        elif (
            "1011" in error_msg
            or "Internal error encountered" in error_msg
            or error_type == "ServerError"
            or "INTERNAL" in error_msg.upper()
        ):
            friendly_error = "The AI provider had a temporary glitch. Please try again."
        elif "400" in error_msg or "invalid" in error_msg.lower() or "unsupported" in error_msg.lower():
            friendly_error = "There was a problem starting the interview configuration. Please try again."
        elif error_msg and error_msg.strip() and error_msg != "None":
            friendly_error = error_msg[:120]
            
        try:
            await send_message(MessageType.SYSTEM, f"Error: {friendly_error}")
        except Exception:
            pass
        try:
            # Surface a meaningful close reason to the client instead of the
            # generic "1011 None" the default FastAPI handler would send.
            await websocket.close(code=1011, reason=friendly_error[:120])
        except Exception:
            pass
    finally:
        if gemini_session:
            transcript_text = gemini_session.get_transcript_text()

            if cancelled or is_practice:
                if is_practice:
                    async with get_connection() as conn:
                        await conn.execute("DELETE FROM interviews WHERE id = $1", interview_id)
                    print(f"[Interview {interview_id}] Practice session ended, record deleted")
                else:
                    # User cancelled — save transcript but skip analysis
                    async with get_connection() as conn:
                        await conn.execute(
                            """
                            UPDATE interviews
                            SET transcript = $1, status = 'cancelled', completed_at = NOW()
                            WHERE id = $2
                            """,
                            transcript_text,
                            interview_id,
                        )
                        if interview_type == "investigation":
                            await conn.execute(
                                "UPDATE ir_investigation_interviews SET status = 'cancelled' WHERE interview_id = $1",
                                interview_id,
                            )
                    print(f"[Interview {interview_id}] Session cancelled by user, skipping analysis")
            else:
                # Save transcript with 'analyzing' status - analysis will run in background worker
                async with get_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE interviews
                        SET transcript = $1, status = 'analyzing', completed_at = NOW()
                        WHERE id = $2
                        """,
                        transcript_text,
                        interview_id,
                    )

                    # For investigation interviews, update junction table
                    if interview_type == "investigation":
                        await conn.execute(
                            "UPDATE ir_investigation_interviews SET status = 'completed', completed_at = NOW() WHERE interview_id = $1",
                            interview_id,
                        )

                # Queue analysis task for Celery worker
                if transcript_text:
                    from app.workers.tasks.interview_analysis import analyze_interview_async

                    analyze_interview_async.delay(
                        interview_id=str(interview_id),
                        interview_type=interview_type,
                        transcript=transcript_text,
                        company_id=str(row["company_id"]) if row["company_id"] else None,
                        culture_profile=culture_profile,
                        language=tutor_language,  # Pass language for tutor_language sessions
                        incident_id=incident_id_str if interview_type == "investigation" else None,
                    )
                    print(f"[Interview {interview_id}] Queued analysis task for background processing")
                else:
                    # No transcript — session failed before any conversation. Reset so candidate can retry.
                    print(f"[Interview {interview_id}] Reset to pending — no transcript captured (type={interview_type})")
                    async with get_connection() as conn:
                        await conn.execute(
                            "UPDATE interviews SET status = 'pending', completed_at = NULL WHERE id = $1",
                            interview_id,
                        )

            await gemini_session.close()

        if "forward_task" in dir() and forward_task:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass

        print(f"[Interview {interview_id}] Session ended")
