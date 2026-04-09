"""Twilio webhook routes — TwiML, Media Stream bridge, status callbacks."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.responses import Response

from ...config import get_settings
from ...core.services.audio_convert import mulaw_8k_to_pcm_16k, pcm_16k_to_mulaw_8k
from ...core.services.gemini_session import GeminiLiveSession
from ...core.services.twilio_call_service import CallResult, get_twilio_call_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.api_route("/twiml/{call_id}", methods=["GET", "POST"])
async def twilio_twiml(call_id: str):
    """Return TwiML that opens a bidirectional Media Stream."""
    from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

    call_service = get_twilio_call_service()
    context = call_service.get_context(call_id)

    response = VoiceResponse()
    if not context:
        response.say("Sorry, this call could not be connected.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    settings = get_settings()
    media_stream_base = settings.twilio_media_stream_url or ""
    stream_url = f"{media_stream_base}/{call_id}"

    connect = Connect()
    stream = Stream(url=stream_url)
    connect.append(stream)
    response.append(connect)

    return Response(content=str(response), media_type="application/xml")


@router.websocket("/media-stream/{call_id}")
async def twilio_media_stream(websocket: WebSocket, call_id: str):
    """Bridge Twilio Media Stream audio ↔ Gemini Live session."""
    await websocket.accept()

    call_service = get_twilio_call_service()
    context = call_service.get_context(call_id)
    if not context:
        logger.warning("No context for call_id %s", call_id)
        await websocket.close()
        return

    settings = get_settings()
    stream_sid = None

    # Create Gemini Live session
    gemini_session = GeminiLiveSession(
        model=settings.live_model,
        voice=settings.voice,
        api_key=settings.gemini_api_key,
    )

    try:
        await gemini_session.connect_raw(system_prompt=context.system_prompt)
    except Exception as exc:
        logger.error("Failed to connect Gemini for call %s: %s", call_id, exc)
        if context.result_future and not context.result_future.done():
            context.result_future.set_result(CallResult(error=f"Gemini connection failed: {exc}"))
        call_service.remove_context(call_id)
        await websocket.close()
        return

    # Tell Gemini to start the conversation
    await gemini_session.send_text(
        f"The phone call has connected. Please introduce yourself and begin asking about: "
        f"{', '.join(context.missing_info)}"
    )

    async def forward_gemini_to_twilio():
        """Send Gemini audio responses back through Twilio."""
        try:
            async for response in gemini_session.receive_responses():
                if response.type == "audio" and response.audio_data and stream_sid:
                    mulaw_audio = pcm_16k_to_mulaw_8k(response.audio_data)
                    payload = base64.b64encode(mulaw_audio).decode("ascii")
                    await websocket.send_json({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": payload},
                    })
        except Exception as exc:
            if not gemini_session._closed:
                logger.warning("Gemini→Twilio forward error: %s", exc)

    forward_task = asyncio.create_task(forward_gemini_to_twilio())

    # Auto-hangup timer
    async def auto_hangup():
        await asyncio.sleep(context.max_duration_seconds)
        logger.info("Auto-hanging up call %s after %ds", call_id, context.max_duration_seconds)
        try:
            await gemini_session.send_text("Please wrap up the conversation now. Thank them and say goodbye.")
        except Exception:
            pass
        await asyncio.sleep(10)
        if context.call_sid:
            await call_service.hangup(context.call_sid)

    hangup_timer = asyncio.create_task(auto_hangup())

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            event = message.get("event")

            if event == "start":
                stream_sid = message["start"]["streamSid"]
                context.call_sid = message["start"].get("callSid", context.call_sid)
                context.started_at = datetime.now(timezone.utc)
                logger.info("Twilio media stream started for call %s", call_id)

            elif event == "media":
                mulaw_data = base64.b64decode(message["media"]["payload"])
                pcm_data = mulaw_8k_to_pcm_16k(mulaw_data)
                await gemini_session.send_audio(pcm_data)

            elif event == "stop":
                logger.info("Twilio media stream stopped for call %s", call_id)
                break

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected for call %s", call_id)
    except Exception as exc:
        logger.error("Twilio media stream error for call %s: %s", call_id, exc)
    finally:
        hangup_timer.cancel()
        forward_task.cancel()

        # Extract transcript
        transcript = gemini_session.get_transcript_text()
        context.transcript = transcript

        # Parse findings from transcript using Gemini analysis
        findings = await _extract_findings_from_transcript(transcript, context.missing_info)
        context.findings = findings

        # Resolve the Future so the caller gets results
        if context.result_future and not context.result_future.done():
            context.result_future.set_result(CallResult(
                transcript=transcript,
                findings=findings,
            ))

        await gemini_session.close()
        call_service.remove_context(call_id)
        logger.info("Call %s completed. Transcript length: %d", call_id, len(transcript))


@router.post("/status/{call_id}")
async def twilio_status_callback(call_id: str, request: Request):
    """Handle Twilio call status updates."""
    form = await request.form()
    call_status = form.get("CallStatus", "")

    logger.info("Twilio status for call %s: %s", call_id, call_status)

    if call_status in ("busy", "no-answer", "failed", "canceled"):
        call_service = get_twilio_call_service()
        context = call_service.remove_context(call_id)
        if context and context.result_future and not context.result_future.done():
            context.result_future.set_result(CallResult(
                error=f"Call {call_status}",
            ))

    return Response(status_code=204)


async def _extract_findings_from_transcript(transcript: str, missing_info: list[str]) -> dict:
    """Use Gemini analysis model to extract structured data from a phone call transcript."""
    if not transcript.strip():
        return {}

    from google import genai

    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    client = genai.Client(api_key=api_key)

    prompt = (
        f"Extract the following information from this phone call transcript "
        f"with an apartment leasing office.\n\n"
        f"INFORMATION NEEDED: {', '.join(missing_info)}\n\n"
        f"TRANSCRIPT:\n{transcript}\n\n"
        f"Return a JSON object with the requested information. Use descriptive key names. "
        f"If information was not obtained, use null. Include a 'call_summary' key."
    )

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.analysis_model,
            contents=prompt,
        )
        raw_text = response.text or ""
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw_text[start:end])
    except Exception as exc:
        logger.warning("Failed to extract findings from call transcript: %s", exc)

    return {}
