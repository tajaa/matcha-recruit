from typing import Optional
from uuid import UUID
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..database import get_connection
from ..models.interview import InterviewCreate, InterviewResponse, InterviewStart, ConversationAnalysis
from ..services.gemini_session import GeminiLiveSession
from ..services.culture_analyzer import CultureAnalyzer
from ..services.conversation_analyzer import ConversationAnalyzer
from ..protocol import (
    MessageType,
    parse_text_message,
    parse_audio_from_client,
    frame_audio_for_client,
    ConversationMessage,
)
from ..config import get_settings

router = APIRouter()


@router.post("/companies/{company_id}/interviews", response_model=InterviewStart)
async def create_interview(company_id: UUID, interview: InterviewCreate):
    """Create a new interview session for a company."""
    async with get_connection() as conn:
        # Verify company exists
        company = await conn.fetchrow(
            "SELECT id FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

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
            websocket_url=f"/ws/interview/{interview_id}",
        )


@router.get("/interviews/{interview_id}", response_model=InterviewResponse)
async def get_interview(interview_id: UUID):
    """Get an interview by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, interviewer_name, interviewer_role, interview_type,
                   transcript, raw_culture_data, conversation_analysis, status, created_at, completed_at
            FROM interviews
            WHERE id = $1
            """,
            interview_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Interview not found")

        raw_culture_data = None
        if row["raw_culture_data"]:
            raw_culture_data = json.loads(row["raw_culture_data"]) if isinstance(row["raw_culture_data"], str) else row["raw_culture_data"]

        conversation_analysis = None
        if row["conversation_analysis"]:
            conversation_analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]

        return InterviewResponse(
            id=row["id"],
            company_id=row["company_id"],
            interviewer_name=row["interviewer_name"],
            interviewer_role=row["interviewer_role"],
            interview_type=row["interview_type"] or "culture",
            transcript=row["transcript"],
            raw_culture_data=raw_culture_data,
            conversation_analysis=conversation_analysis,
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )


@router.get("/companies/{company_id}/interviews", response_model=list[InterviewResponse])
async def list_company_interviews(company_id: UUID):
    """List all interviews for a company."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, company_id, interviewer_name, interviewer_role, interview_type,
                   transcript, raw_culture_data, conversation_analysis, status, created_at, completed_at
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
            results.append(InterviewResponse(
                id=row["id"],
                company_id=row["company_id"],
                interviewer_name=row["interviewer_name"],
                interviewer_role=row["interviewer_role"],
                interview_type=row["interview_type"] or "culture",
                transcript=row["transcript"],
                raw_culture_data=raw_culture_data,
                conversation_analysis=conversation_analysis,
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            ))
        return results


@router.post("/companies/{company_id}/aggregate-culture")
async def aggregate_culture(company_id: UUID):
    """Aggregate all interview culture data into a company profile."""
    settings = get_settings()
    analyzer = CultureAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    async with get_connection() as conn:
        # Get all completed interviews for this company
        rows = await conn.fetch(
            """
            SELECT raw_culture_data
            FROM interviews
            WHERE company_id = $1 AND status = 'completed' AND raw_culture_data IS NOT NULL
            """,
            company_id,
        )

        if not rows:
            raise HTTPException(status_code=400, detail="No completed interviews with culture data")

        # Parse culture data from all interviews
        culture_data_list = []
        for row in rows:
            if row["raw_culture_data"]:
                data = json.loads(row["raw_culture_data"]) if isinstance(row["raw_culture_data"], str) else row["raw_culture_data"]
                culture_data_list.append(data)

        # Aggregate using the analyzer
        aggregated = await analyzer.aggregate_culture_profiles(culture_data_list)

        # Upsert the culture profile
        await conn.execute(
            """
            INSERT INTO culture_profiles (company_id, profile_data, last_updated)
            VALUES ($1, $2, NOW())
            ON CONFLICT (company_id)
            DO UPDATE SET profile_data = $2, last_updated = NOW()
            """,
            company_id,
            json.dumps(aggregated),
        )

        return {"status": "aggregated", "profile": aggregated}


@router.get("/interviews/{interview_id}/analysis")
async def get_interview_analysis(interview_id: UUID):
    """Get the conversation analysis for an interview."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT conversation_analysis
            FROM interviews
            WHERE id = $1
            """,
            interview_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Interview not found")

        if not row["conversation_analysis"]:
            raise HTTPException(status_code=404, detail="Analysis not yet generated for this interview")

        analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]
        return analysis


@router.post("/interviews/{interview_id}/analyze")
async def analyze_interview(interview_id: UUID):
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

        if row["status"] != "completed":
            raise HTTPException(status_code=400, detail="Interview must be completed before analysis")

        if not row["transcript"]:
            raise HTTPException(status_code=400, detail="Interview has no transcript to analyze")

        # For candidate interviews, fetch culture profile
        culture_profile = None
        if row["interview_type"] == "candidate":
            culture_row = await conn.fetchrow(
                "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
                row["company_id"],
            )
            if culture_row and culture_row["profile_data"]:
                culture_profile = json.loads(culture_row["profile_data"]) if isinstance(culture_row["profile_data"], str) else culture_row["profile_data"]

        # Run analysis
        conv_analyzer = ConversationAnalyzer(
            api_key=settings.gemini_api_key,
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
            model=settings.analysis_model,
        )

        analysis = await conv_analyzer.analyze_interview(
            transcript=row["transcript"],
            interview_type=row["interview_type"] or "culture",
            culture_profile=culture_profile,
        )

        # Store analysis
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


# WebSocket endpoint for voice interviews
@router.websocket("/ws/interview/{interview_id}")
async def interview_websocket(websocket: WebSocket, interview_id: UUID):
    """WebSocket endpoint for voice interview sessions."""
    await websocket.accept()

    settings = get_settings()
    gemini_session: Optional[GeminiLiveSession] = None
    analyzer = CultureAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    # Get interview and company info
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.id, i.company_id, i.interviewer_name, i.interviewer_role, i.interview_type, c.name as company_name
            FROM interviews i
            JOIN companies c ON i.company_id = c.id
            WHERE i.id = $1
            """,
            interview_id,
        )
        if not row:
            await websocket.close(code=4004, reason="Interview not found")
            return

        company_name = row["company_name"]
        interviewer_name = row["interviewer_name"] or "HR Representative"
        interviewer_role = row["interviewer_role"] or "HR"
        interview_type = row["interview_type"] or "culture"

        # For candidate interviews, fetch the company's culture profile
        culture_profile = None
        if interview_type == "candidate":
            culture_row = await conn.fetchrow(
                "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
                row["company_id"],
            )
            if culture_row and culture_row["profile_data"]:
                culture_profile = json.loads(culture_row["profile_data"]) if isinstance(culture_row["profile_data"], str) else culture_row["profile_data"]

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
        # Create Gemini session
        gemini_session = GeminiLiveSession(
            model=settings.live_model,
            voice=settings.voice,
            api_key=settings.gemini_api_key,
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
        )

        # Connect with appropriate interview prompt
        await gemini_session.connect(
            company_name=company_name,
            interviewer_name=interviewer_name,
            interviewer_role=interviewer_role,
            interview_type=interview_type,
            culture_profile=culture_profile,
        )

        await send_message(MessageType.STATUS, "Interview session started")

        # Trigger the model to speak first
        if interview_type == "candidate":
            await gemini_session.send_text("Please start the interview now. Greet the candidate warmly and begin.")
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
                elif response.type == "turn_complete":
                    await send_message(MessageType.STATUS, "ready")

        forward_task = asyncio.create_task(forward_responses())

        # Handle incoming messages
        while True:
            message = await websocket.receive()

            if "text" in message:
                cmd = parse_text_message(message["text"])
                if cmd and cmd.command == "stop_session":
                    break
                elif cmd and cmd.command == "send_text":
                    # Allow sending text messages (for testing)
                    if hasattr(cmd, "text") and cmd.text:
                        await gemini_session.send_text(cmd.text)

            elif "bytes" in message:
                audio_data = parse_audio_from_client(message["bytes"])
                if audio_data:
                    await gemini_session.send_audio(audio_data)

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
        print(f"[Interview {interview_id}] Error: {e}")
        try:
            await send_message(MessageType.SYSTEM, f"Error: {str(e)}")
        except Exception:
            pass
    finally:
        # Save transcript and extract culture data
        if gemini_session:
            transcript_text = gemini_session.get_transcript_text()
            culture_data = None
            conversation_analysis_data = None

            if transcript_text:
                # Extract culture data from transcript
                try:
                    culture_data = await analyzer.extract_culture_from_transcript(transcript_text)
                except Exception as e:
                    print(f"[Interview {interview_id}] Failed to extract culture: {e}")

                # Generate conversation analysis
                try:
                    conv_analyzer = ConversationAnalyzer(
                        api_key=settings.gemini_api_key,
                        vertex_project=settings.vertex_project,
                        vertex_location=settings.vertex_location,
                        model=settings.analysis_model,
                    )
                    conversation_analysis_data = await conv_analyzer.analyze_interview(
                        transcript=transcript_text,
                        interview_type=interview_type,
                        culture_profile=culture_profile,
                    )
                except Exception as e:
                    print(f"[Interview {interview_id}] Failed to generate conversation analysis: {e}")

            async with get_connection() as conn:
                await conn.execute(
                    """
                    UPDATE interviews
                    SET transcript = $1, raw_culture_data = $2, conversation_analysis = $3,
                        status = 'completed', completed_at = NOW()
                    WHERE id = $4
                    """,
                    transcript_text,
                    json.dumps(culture_data) if culture_data else None,
                    json.dumps(conversation_analysis_data) if conversation_analysis_data else None,
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
