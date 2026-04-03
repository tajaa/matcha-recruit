"""Twilio outbound call service for research phone calls."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from ...config import get_settings

logger = logging.getLogger(__name__)

PHONE_CALL_PROMPT = """You are a friendly, professional assistant calling an apartment leasing office on behalf of a prospective renter.

YOU ARE CALLING: {apartment_name}
INFORMATION NEEDED: {missing_info}

CALL PROTOCOL:
1. When the call connects, introduce yourself: "Hi, I'm calling to get some information about {apartment_name}. I'm helping a friend who's looking at apartments."
2. Ask about each piece of missing information, one at a time.
3. Be polite, concise, and natural. Don't read from a script.
4. If they put you on hold, wait patiently.
5. If you reach voicemail, leave a brief message and note that you reached voicemail.
6. When you have all the information (or they can't provide it), thank them and end the call.
7. If they ask for contact info, say "They'll reach out directly, I'm just gathering initial information."

IMPORTANT:
- This is a real phone call — speak naturally and at a normal pace
- Keep your questions short and direct
- Don't ask more than one question at a time
- Listen carefully to their answers
- If they give partial information, ask a clarifying follow-up
- The call should last no more than 3-4 minutes
"""


@dataclass
class CallContext:
    call_id: str
    apartment_name: str
    phone_number: str
    missing_info: list[str]
    system_prompt: str
    call_sid: Optional[str] = None
    result_future: Optional[asyncio.Future] = None
    transcript: str = ""
    findings: dict = field(default_factory=dict)
    started_at: Optional[datetime] = None
    max_duration_seconds: int = 300


@dataclass
class CallResult:
    transcript: str = ""
    findings: dict = field(default_factory=dict)
    error: Optional[str] = None


_instance: Optional[TwilioCallService] = None


class TwilioCallService:
    def __init__(self):
        settings = get_settings()
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.from_number = settings.twilio_phone_number
        self.media_stream_url = settings.twilio_media_stream_url
        self._pending_calls: dict[str, CallContext] = {}

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number)

    async def initiate_call(self, to_number: str, context: CallContext) -> str:
        """Start an outbound call. Returns call_id."""
        from twilio.rest import Client

        client = Client(self.account_sid, self.auth_token)

        self._pending_calls[context.call_id] = context

        # TwiML URL that Twilio will request when call connects
        settings = get_settings()
        base_url = settings.app_base_url.rstrip("/")
        twiml_url = f"{base_url}/api/twilio/twiml/{context.call_id}"
        status_url = f"{base_url}/api/twilio/status/{context.call_id}"

        def _create():
            return client.calls.create(
                to=to_number,
                from_=self.from_number,
                url=twiml_url,
                status_callback=status_url,
                timeout=30,
                time_limit=context.max_duration_seconds,
            )

        call = await asyncio.to_thread(_create)
        context.call_sid = call.sid
        logger.info("Twilio call initiated: %s → %s (call_id=%s)", self.from_number, to_number, context.call_id)
        return context.call_id

    async def initiate_and_wait(
        self,
        to_number: str,
        apartment_name: str,
        missing_info: list[str],
        timeout: int = 330,
    ) -> CallResult:
        """Initiate a call and wait for results."""
        call_id = str(uuid4())
        system_prompt = PHONE_CALL_PROMPT.format(
            apartment_name=apartment_name,
            missing_info=", ".join(missing_info),
        )
        future: asyncio.Future[CallResult] = asyncio.get_running_loop().create_future()

        context = CallContext(
            call_id=call_id,
            apartment_name=apartment_name,
            phone_number=to_number,
            missing_info=missing_info,
            system_prompt=system_prompt,
            result_future=future,
        )

        await self.initiate_call(to_number, context)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Phone call timed out for %s", to_number)
            self._pending_calls.pop(call_id, None)
            return CallResult(error="Call timed out")

    def get_context(self, call_id: str) -> Optional[CallContext]:
        return self._pending_calls.get(call_id)

    def remove_context(self, call_id: str) -> Optional[CallContext]:
        return self._pending_calls.pop(call_id, None)

    async def hangup(self, call_sid: str) -> None:
        from twilio.rest import Client

        client = Client(self.account_sid, self.auth_token)

        def _update():
            client.calls(call_sid).update(status="completed")

        try:
            await asyncio.to_thread(_update)
        except Exception as exc:
            logger.warning("Failed to hang up call %s: %s", call_sid, exc)


def get_twilio_call_service() -> TwilioCallService:
    global _instance
    if _instance is None:
        _instance = TwilioCallService()
    return _instance


def normalize_phone_number(raw: str) -> Optional[str]:
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    return None
